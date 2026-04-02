"""
Amazon Advertising & Sales Intelligence Agent — FastAPI Backend
"""

import io
import json
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from agent import run_agent
from models import AgentResponse, MetricsResponse, QueryRequest
from tools import (
    keyword_performance_evaluator,
    sales_trend_analyzer,
    spend_vs_revenue_calculator,
)

app = FastAPI(title="Amazon Ad & Sales Intelligence Agent", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory data store
DATA_STORE: dict = {
    "sales_df": None,
    "ad_df": None,
}

DATA_DIR = Path(__file__).parent.parent / "data"


def load_default_data():
    """Load sample data from data/ directory if present."""
    sales_path = DATA_DIR / "sales_data.csv"
    ad_path = DATA_DIR / "keyword_ad_data.csv"
    if sales_path.exists() and ad_path.exists():
        DATA_STORE["sales_df"] = pd.read_csv(sales_path)
        DATA_STORE["ad_df"] = pd.read_csv(ad_path)
        print("✅ Default data loaded from data/ directory")


@app.on_event("startup")
async def startup():
    load_default_data()


def get_dataframes():
    if DATA_STORE["sales_df"] is None or DATA_STORE["ad_df"] is None:
        raise HTTPException(
            status_code=400,
            detail="No data loaded. Please upload CSV files via POST /upload first.",
        )
    return DATA_STORE["sales_df"], DATA_STORE["ad_df"]


# ─── Endpoints ────────────────────────────────────────────────────────────────


@app.get("/")
def root():
    return {
        "status": "running",
        "message": "Amazon Ad & Sales Intelligence Agent API",
        "data_loaded": DATA_STORE["sales_df"] is not None,
        "endpoints": ["/upload", "/query", "/metrics"],
    }


@app.post("/upload")
async def upload_files(
    sales_file: UploadFile = File(..., description="Sales CSV"),
    ads_file: UploadFile = File(..., description="Keyword Ad CSV"),
):
    """Upload sales.csv and ads.csv files."""
    try:
        sales_content = await sales_file.read()
        ads_content = await ads_file.read()

        sales_df = pd.read_csv(io.BytesIO(sales_content))
        ad_df = pd.read_csv(io.BytesIO(ads_content))

        # Basic validation
        required_sales = {"asin", "date", "units_sold", "revenue"}
        required_ads = {"asin", "keyword", "ad_spend", "attributed_sales", "acos"}

        if not required_sales.issubset(set(sales_df.columns)):
            raise HTTPException(400, f"Sales CSV missing columns: {required_sales - set(sales_df.columns)}")
        if not required_ads.issubset(set(ad_df.columns)):
            raise HTTPException(400, f"Ads CSV missing columns: {required_ads - set(ad_df.columns)}")

        DATA_STORE["sales_df"] = sales_df
        DATA_STORE["ad_df"] = ad_df

        return {
            "status": "success",
            "sales_rows": len(sales_df),
            "ads_rows": len(ad_df),
            "sales_asins": int(sales_df["asin"].nunique()),
            "ads_asins": int(ad_df["asin"].nunique()),
            "date_range_sales": {
                "start": str(pd.to_datetime(sales_df["date"]).min().date()),
                "end": str(pd.to_datetime(sales_df["date"]).max().date()),
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Error processing files: {str(e)}")


@app.post("/query")
async def query_agent(request: QueryRequest):
    """Submit a natural language query to the agent."""
    sales_df, ad_df = get_dataframes()
    try:
        result = run_agent(request.query, sales_df, ad_df)
        return result
    except Exception as e:
        raise HTTPException(500, f"Agent error: {str(e)}")


@app.get("/metrics")
async def get_metrics():
    """Return overall KPI metrics for the dashboard."""
    sales_df, ad_df = get_dataframes()

    try:
        sales_df["date"] = pd.to_datetime(sales_df["date"])
        ad_df["date"] = pd.to_datetime(ad_df["date"])

        total_revenue = float(sales_df["revenue"].sum())
        total_units = int(sales_df["units_sold"].sum())
        total_spend = float(ad_df["ad_spend"].sum())
        total_attributed = float(ad_df["attributed_sales"].sum())
        organic_rev = max(0, total_revenue - total_attributed)
        overall_acos = (total_spend / total_attributed * 100) if total_attributed > 0 else 999

        # Profit (use profit_margin_pct if present, else estimate)
        if "profit_margin_pct" in sales_df.columns:
            avg_margin = sales_df["profit_margin_pct"].mean() / 100
            total_profit = total_revenue * avg_margin
        else:
            total_profit = total_revenue - total_spend

        # Top ASINs by revenue
        top_asins = (
            sales_df.groupby(["asin", "product_title"])
            .agg(revenue=("revenue", "sum"), units=("units_sold", "sum"))
            .sort_values("revenue", ascending=False)
            .head(5)
            .reset_index()
            .to_dict(orient="records")
        )

        # Daily revenue trend (last 30 days)
        daily = (
            sales_df.groupby("date")
            .agg(revenue=("revenue", "sum"), units=("units_sold", "sum"))
            .reset_index()
            .sort_values("date")
            .tail(30)
        )
        daily["date"] = daily["date"].dt.strftime("%Y-%m-%d")
        daily_trend = daily.to_dict(orient="records")

        # Daily spend trend
        spend_daily = (
            ad_df.groupby("date")
            .agg(spend=("ad_spend", "sum"), attributed=("attributed_sales", "sum"))
            .reset_index()
            .sort_values("date")
            .tail(30)
        )
        spend_daily["date"] = spend_daily["date"].dt.strftime("%Y-%m-%d")
        spend_trend = spend_daily.to_dict(orient="records")

        return {
            "total_revenue": round(total_revenue, 2),
            "total_ad_spend": round(total_spend, 2),
            "total_profit": round(total_profit, 2),
            "overall_acos": round(overall_acos, 2),
            "total_units_sold": total_units,
            "total_attributed_sales": round(total_attributed, 2),
            "organic_revenue": round(organic_rev, 2),
            "ad_contribution_pct": round(
                (total_attributed / total_revenue * 100) if total_revenue > 0 else 0, 2
            ),
            "top_asins": top_asins,
            "daily_trend": daily_trend,
            "spend_trend": spend_trend,
        }

    except Exception as e:
        raise HTTPException(500, f"Metrics error: {str(e)}")


@app.get("/asins")
async def list_asins():
    """List all available ASINs."""
    sales_df, ad_df = get_dataframes()
    sales_asins = set(sales_df["asin"].unique())
    ad_asins = set(ad_df["asin"].unique())
    return {
        "sales_asins": sorted(list(sales_asins)),
        "ad_asins": sorted(list(ad_asins)),
        "common_asins": sorted(list(sales_asins & ad_asins)),
    }
