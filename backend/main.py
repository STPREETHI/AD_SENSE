"""
Amazon Advertising & Sales Intelligence Agent — FastAPI Backend
API keys are loaded from .env — never exposed to the frontend.
"""

import io
import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Load .env before anything else
load_dotenv()

from agent import run_agent
from models import QueryRequest

app = FastAPI(title="Amazon Ad & Sales Intelligence Agent", version="2.0.0")

# CORS — allow null origin for local file:// dev + configured origins
ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,http://localhost:5500,http://127.0.0.1:5500,"
    "http://localhost:8000,http://127.0.0.1:8000"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*", "null"],   # "null" covers requests from file:// pages
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

# In-memory data store
DATA_STORE: dict = {"sales_df": None, "ad_df": None}
DATA_DIR = Path(__file__).parent / "data"

# ── Serve frontend from /  ────────────────────────────────────────────────────
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


def load_default_data():
    sales_path = DATA_DIR / "sales_data.csv"
    ad_path    = DATA_DIR / "keyword_ad_data.csv"
    if sales_path.exists() and ad_path.exists():
        DATA_STORE["sales_df"] = pd.read_csv(sales_path)
        DATA_STORE["ad_df"]    = pd.read_csv(ad_path)
        print("Default data loaded from data/ directory")


@app.on_event("startup")
async def startup():
    load_default_data()
    provider = os.getenv("AI_PROVIDER", "gemini")
    key_set  = bool(os.getenv("GEMINI_API_KEY") or os.getenv("GROQ_API_KEY"))
    print(f"AI provider: {provider} | Key configured: {key_set}")
    if FRONTEND_DIR.exists():
        print(f"Frontend served at http://localhost:8000/  ({FRONTEND_DIR})")
    else:
        print(f"WARNING: Frontend directory not found at {FRONTEND_DIR}")


def get_dataframes():
    if DATA_STORE["sales_df"] is None or DATA_STORE["ad_df"] is None:
        raise HTTPException(
            status_code=400,
            detail="No data loaded. Upload CSV files via POST /upload first.",
        )
    return DATA_STORE["sales_df"], DATA_STORE["ad_df"]


# ── API Endpoints (must be defined BEFORE the static mount) ──────────────────

@app.get("/api/status")
@app.get("/status")
def root():
    provider = os.getenv("AI_PROVIDER", "gemini")
    key_ok   = bool(os.getenv("GEMINI_API_KEY") if provider == "gemini"
                    else os.getenv("GROQ_API_KEY"))
    return {
        "status":       "running",
        "ai_provider":  provider,
        "ai_key_set":   key_ok,
        "data_loaded":  DATA_STORE["sales_df"] is not None,
        "endpoints":    ["/upload", "/query", "/metrics"],
    }


# Keep the old root for backward compat (returns JSON, not the page)
@app.get("/status")
def status():
    return root()


@app.post("/upload")
async def upload_files(
    sales_file: UploadFile = File(...),
    ads_file:   UploadFile = File(...),
):
    try:
        sales_df = pd.read_csv(io.BytesIO(await sales_file.read()))
        ad_df    = pd.read_csv(io.BytesIO(await ads_file.read()))

        required_sales = {"asin", "date", "units_sold", "revenue"}
        required_ads   = {"asin", "keyword", "ad_spend", "attributed_sales"}

        missing_sales = required_sales - set(sales_df.columns)
        missing_ads   = required_ads   - set(ad_df.columns)
        if missing_sales:
            raise HTTPException(400, f"Sales CSV missing columns: {missing_sales}")
        if missing_ads:
            raise HTTPException(400, f"Ads CSV missing columns: {missing_ads}")

        DATA_STORE["sales_df"] = sales_df
        DATA_STORE["ad_df"]    = ad_df

        return {
            "status":     "success",
            "sales_rows": len(sales_df),
            "ads_rows":   len(ad_df),
            "sales_asins": int(sales_df["asin"].nunique()),
            "ads_asins":   int(ad_df["asin"].nunique()),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Error processing files: {e}")


@app.post("/query")
async def query_agent(request: QueryRequest):
    sales_df, ad_df = get_dataframes()
    try:
        result = await run_agent(request.query, sales_df, ad_df)
        return result
    except Exception as e:
        raise HTTPException(500, f"Agent error: {e}")


@app.get("/metrics")
async def get_metrics():
    sales_df, ad_df = get_dataframes()
    try:
        sales_df = sales_df.copy()
        ad_df    = ad_df.copy()
        sales_df["date"] = pd.to_datetime(sales_df["date"])
        ad_df["date"]    = pd.to_datetime(ad_df["date"])

        total_revenue    = float(sales_df["revenue"].sum())
        total_units      = int(sales_df["units_sold"].sum())
        total_spend      = float(ad_df["ad_spend"].sum())
        total_attributed = float(ad_df["attributed_sales"].sum())
        total_clicks     = int(ad_df["clicks"].sum())
        total_impr       = int(ad_df["impressions"].sum())
        total_attr_units = int(ad_df["attributed_units"].sum())
        organic_rev      = max(0.0, total_revenue - total_attributed)
        overall_acos     = (total_spend / total_attributed * 100) if total_attributed > 0 else 999.0
        overall_roas     = (total_attributed / total_spend) if total_spend > 0 else 0.0
        ctr              = (total_clicks / total_impr  * 100) if total_impr   > 0 else 0.0
        cvr              = (total_attr_units / total_clicks * 100) if total_clicks > 0 else 0.0
        avg_cpc          = total_spend / total_clicks if total_clicks > 0 else 0.0

        profit_rows = sales_df[sales_df["profit_margin_pct"].notna() & (sales_df["profit_margin_pct"] > 0)]
        avg_margin  = (profit_rows["profit_margin_pct"].mean() / 100) if len(profit_rows) > 0 else 0.20
        total_profit = total_revenue * avg_margin - total_spend

        kw = (
            ad_df.groupby(["asin", "keyword"])
                 .agg(clicks=("clicks","sum"), attr_units=("attributed_units","sum"),
                      spend=("ad_spend","sum"))
                 .reset_index()
        )
        wasted = float(kw[(kw["clicks"] > 0) & (kw["attr_units"] == 0)]["spend"].sum())

        top_asins = (
            sales_df.groupby(["asin", "product_title"])
                    .agg(revenue=("revenue","sum"), units=("units_sold","sum"))
                    .sort_values("revenue", ascending=False)
                    .head(10)
                    .reset_index()
                    .to_dict(orient="records")
        )

        daily = (
            sales_df.groupby("date")
                    .agg(revenue=("revenue","sum"), units=("units_sold","sum"))
                    .reset_index()
                    .sort_values("date")
                    .tail(30)
        )
        daily["date"] = daily["date"].dt.strftime("%Y-%m-%d")

        spend_daily = (
            ad_df.groupby("date")
                 .agg(spend=("ad_spend","sum"), attributed=("attributed_sales","sum"))
                 .reset_index()
                 .sort_values("date")
                 .tail(30)
        )
        spend_daily["date"] = spend_daily["date"].dt.strftime("%Y-%m-%d")

        return {
            "total_revenue":        round(total_revenue, 2),
            "total_ad_spend":       round(total_spend, 2),
            "total_profit":         round(total_profit, 2),
            "overall_acos":         round(overall_acos, 2),
            "overall_roas":         round(overall_roas, 2),
            "total_units_sold":     total_units,
            "total_attributed_sales": round(total_attributed, 2),
            "organic_revenue":      round(organic_rev, 2),
            "ad_contribution_pct":  round(
                total_attributed / total_revenue * 100 if total_revenue > 0 else 0, 2
            ),
            "total_clicks":         total_clicks,
            "total_impressions":    total_impr,
            "avg_ctr":              round(ctr, 2),
            "avg_cvr":              round(cvr, 2),
            "avg_cpc":              round(avg_cpc, 2),
            "wasted_spend":         round(wasted, 2),
            "top_asins":            top_asins,
            "daily_trend":          daily.to_dict(orient="records"),
            "spend_trend":          spend_daily.to_dict(orient="records"),
        }
    except Exception as e:
        raise HTTPException(500, f"Metrics error: {e}")


@app.get("/config")
def config_status():
    provider = os.getenv("AI_PROVIDER", "gemini")
    return {
        "ai_provider":    provider,
        "model":          os.getenv("GEMINI_MODEL" if provider == "gemini" else "GROQ_MODEL"),
        "api_key_set":    bool(
            os.getenv("GEMINI_API_KEY") if provider == "gemini"
            else os.getenv("GROQ_API_KEY")
        ),
    }


# ── Serve frontend static files — MUST be mounted AFTER all API routes ────────
# Access the UI at: http://localhost:8000
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")