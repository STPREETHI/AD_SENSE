"""
Amazon Advertising & Sales Intelligence Agent.
Calls Gemini or Groq from the BACKEND using keys stored in .env
Frontend never sees or handles any API keys.
"""

import json
import os
import re
import httpx
import pandas as pd
from typing import Optional

from tools import (
    sales_trend_analyzer,
    keyword_performance_evaluator,
    spend_vs_revenue_calculator,
    action_recommender,
)

# ── Load provider config from environment ─────────────────────────────────────
AI_PROVIDER   = os.getenv("AI_PROVIDER",   "gemini").lower()
GEMINI_KEY    = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL  = os.getenv("GEMINI_MODEL",  "gemini-1.5-flash")
GROQ_KEY      = os.getenv("GROQ_API_KEY",  "")
GROQ_MODEL    = os.getenv("GROQ_MODEL",    "llama-3.3-70b-versatile")

SYSTEM_PROMPT = """You are an expert Amazon advertising analyst.
You have access to REAL data from an Amazon seller's account.

Analyze the data carefully and answer the user's SPECIFIC question with precise numbers.
Do NOT give generic answers — every response must reference specific keywords, ASINs, or metrics.

RULES:
1. Answer the SPECIFIC question asked — focus only on what was asked
2. Use ACTUAL numbers from the provided data in every finding
3. Connect ad data to sales outcomes (cross-dataset reasoning)
4. Be direct, specific, and actionable

Return ONLY a valid JSON object with EXACTLY this structure (no markdown, no extra text):
{
  "query_understanding": "one sentence explaining what exactly you analyzed",
  "analysis_steps": ["step1 with specific action taken", "step2", "step3", "step4"],
  "key_findings": [
    "Finding 1 with specific numbers from the data",
    "Finding 2",
    "Finding 3",
    "Finding 4",
    "Finding 5"
  ],
  "cross_dataset_insight": "2-3 sentences connecting ad performance to sales outcomes using specific numbers",
  "recommendations": [
    {
      "action": "Specific action to take",
      "reason": "Specific reason with numbers from data",
      "confidence": "High|Medium|Low",
      "expected_impact": "Specific expected outcome"
    }
  ],
  "risk_warnings": ["Warning if critical risk found, else empty array"]
}"""


# ── AI Callers ────────────────────────────────────────────────────────────────

async def call_gemini(user_prompt: str) -> str:
    if not GEMINI_KEY:
        raise ValueError("GEMINI_API_KEY not set in .env")
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent?key={GEMINI_KEY}"
    )
    body = {
        "contents": [{"role": "user", "parts": [{"text": f"{SYSTEM_PROMPT}\n\n{user_prompt}"}]}],
        "generationConfig": {
            "temperature": 0.15,
            "maxOutputTokens": 2000,
            "responseMimeType": "application/json",
        },
    }
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(url, json=body)
        r.raise_for_status()
        data = r.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]


async def call_groq(user_prompt: str) -> str:
    if not GROQ_KEY:
        raise ValueError("GROQ_API_KEY not set in .env")
    url = "https://api.groq.com/openai/v1/chat/completions"
    body = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_prompt},
        ],
        "temperature": 0.15,
        "max_tokens": 2000,
        "response_format": {"type": "json_object"},
    }
    headers = {"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(url, json=body, headers=headers)
        r.raise_for_status()
        data = r.json()
    return data["choices"][0]["message"]["content"]


async def call_ai(user_prompt: str) -> dict:
    """Route to configured AI provider and parse JSON response."""
    if AI_PROVIDER == "groq":
        raw = await call_groq(user_prompt)
    else:
        raw = await call_gemini(user_prompt)

    # Strip markdown fences if any
    clean = re.sub(r"```json\s*", "", raw)
    clean = re.sub(r"```\s*",     "", clean).strip()
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", clean, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise ValueError(f"AI returned non-JSON response: {clean[:200]}")


# ── Data Summarizer ───────────────────────────────────────────────────────────

def build_data_summary(sales_df: pd.DataFrame, ad_df: pd.DataFrame,
                        asin: Optional[str] = None) -> dict:
    """
    Compute all key metrics from both dataframes and return a compact
    structured summary to pass to the AI as context.
    """
    s = sales_df.copy()
    a = ad_df.copy()
    s["date"] = pd.to_datetime(s["date"])
    a["date"] = pd.to_datetime(a["date"])

    if asin:
        s = s[s["asin"] == asin]
        a = a[a["asin"] == asin]

    # ── Sales metrics ─────────────────────────────────────────────────────────
    total_revenue = float(s["revenue"].sum())
    total_units   = int(s["units_sold"].sum())

    max_date  = s["date"].max()
    week_ago  = max_date - pd.Timedelta(days=7)
    recent_rev = float(s[s["date"] > week_ago]["revenue"].sum())
    prev_rev   = float(s[s["date"] <= week_ago]["revenue"].sum())
    wow_change = ((recent_rev - prev_rev) / prev_rev * 100) if prev_rev > 0 else 0.0

    top_products = (
        s.groupby(["asin", "product_title"])
         .agg(revenue=("revenue", "sum"), units=("units_sold", "sum"))
         .sort_values("revenue", ascending=False)
         .head(5)
         .reset_index()
         .assign(revenue=lambda df: df["revenue"].round(0).astype(int),
                 units=lambda df: df["units"].astype(int))
         .to_dict(orient="records")
    )

    # ── Ad metrics ────────────────────────────────────────────────────────────
    total_spend  = float(a["ad_spend"].sum())
    total_attr   = float(a["attributed_sales"].sum())
    total_clicks = int(a["clicks"].sum())
    total_impr   = int(a["impressions"].sum())
    total_attr_u = int(a["attributed_units"].sum())

    overall_acos = (total_spend / total_attr * 100) if total_attr > 0 else 999.0
    overall_roas = (total_attr / total_spend)        if total_spend > 0 else 0.0
    ctr  = (total_clicks / total_impr  * 100) if total_impr   > 0 else 0.0
    cvr  = (total_attr_u / total_clicks * 100) if total_clicks > 0 else 0.0
    avg_cpc = total_spend / total_clicks if total_clicks > 0 else 0.0

    # ── Keyword-level aggregation ─────────────────────────────────────────────
    kw = (
        a.groupby(["asin", "keyword", "match_type"])
         .agg(
             spend=("ad_spend", "sum"),
             attr_sales=("attributed_sales", "sum"),
             attr_units=("attributed_units", "sum"),
             clicks=("clicks", "sum"),
             impressions=("impressions", "sum"),
         )
         .reset_index()
    )
    kw["acos"] = kw.apply(
        lambda r: round(r["spend"] / r["attr_sales"] * 100, 1)
                  if r["attr_sales"] > 0 else 999.0, axis=1
    )
    kw["roas"] = kw.apply(
        lambda r: round(r["attr_sales"] / r["spend"], 2)
                  if r["spend"] > 0 else 0.0, axis=1
    )
    kw["ctr"] = kw.apply(
        lambda r: round(r["clicks"] / r["impressions"] * 100, 2)
                  if r["impressions"] > 0 else 0.0, axis=1
    )
    kw["cvr"] = kw.apply(
        lambda r: round(r["attr_units"] / r["clicks"] * 100, 2)
                  if r["clicks"] > 0 else 0.0, axis=1
    )

    high_acos = kw[(kw["acos"] > 70) & (kw["spend"] > 50)].sort_values("spend", ascending=False)
    zero_conv = kw[(kw["clicks"] > 5) & (kw["attr_units"] == 0)].sort_values("spend", ascending=False)
    top_roas  = kw[kw["roas"] > 0].sort_values("roas", ascending=False).head(8)
    top_spend = kw.sort_values("spend", ascending=False).head(8)
    wasted    = float(high_acos["spend"].sum()) + float(zero_conv["spend"].sum())

    def kw_records(frame, cols, n=8):
        return (frame[cols].head(n)
                .round(2)
                .to_dict(orient="records"))

    cols = ["asin", "keyword", "match_type", "spend", "attr_sales", "acos", "roas", "ctr", "cvr"]

    # ── Match type breakdown ──────────────────────────────────────────────────
    match_breakdown = (
        a.groupby("match_type")
         .agg(spend=("ad_spend","sum"), attr=("attributed_sales","sum"), clicks=("clicks","sum"))
         .reset_index()
         .assign(
             acos=lambda df: (df["spend"] / df["attr"] * 100).where(df["attr"] > 0, 999).round(1),
             roas=lambda df: (df["attr"] / df["spend"]).where(df["spend"] > 0, 0).round(2),
         )
         .to_dict(orient="records")
    )

    # ── Per-ASIN ad performance ───────────────────────────────────────────────
    asin_perf = (
        a.groupby("asin")
         .agg(spend=("ad_spend","sum"), attr=("attributed_sales","sum"), clicks=("clicks","sum"))
         .reset_index()
         .assign(
             roas=lambda df: (df["attr"] / df["spend"]).where(df["spend"] > 0, 0).round(2),
             acos=lambda df: (df["spend"] / df["attr"] * 100).where(df["attr"] > 0, 999).round(1),
         )
         .sort_values("roas", ascending=False)
         .head(6)
         .to_dict(orient="records")
    )

    organic_rev   = max(0.0, total_revenue - total_attr)
    ad_contrib    = (total_attr / total_revenue * 100) if total_revenue > 0 else 0.0

    return {
        "sales": {
            "total_revenue": round(total_revenue, 0),
            "total_units": total_units,
            "revenue_wow_change_pct": round(wow_change, 1),
            "trend": "UP" if wow_change > 2 else ("DOWN" if wow_change < -2 else "STABLE"),
            "date_range": {
                "start": str(s["date"].min().date()),
                "end":   str(s["date"].max().date()),
            },
            "organic_revenue": round(organic_rev, 0),
            "ad_contribution_pct": round(ad_contrib, 1),
            "organic_contribution_pct": round(100 - ad_contrib, 1),
            "top_products": top_products,
        },
        "ads": {
            "total_spend": round(total_spend, 0),
            "total_attributed_sales": round(total_attr, 0),
            "total_clicks": total_clicks,
            "total_impressions": total_impr,
            "overall_acos_pct": round(overall_acos, 1),
            "overall_roas": round(overall_roas, 2),
            "avg_ctr_pct": round(ctr, 2),
            "avg_cvr_pct": round(cvr, 2),
            "avg_cpc": round(avg_cpc, 2),
            "wasted_spend_estimate": round(wasted, 0),
            "high_acos_keyword_count": int(len(high_acos)),
            "zero_conversion_keyword_count": int(len(zero_conv)),
            "high_acos_keywords": kw_records(high_acos, cols),
            "zero_conversion_keywords": kw_records(zero_conv, cols),
            "top_roas_keywords": kw_records(top_roas, cols),
            "top_spend_keywords": kw_records(top_spend, cols),
            "match_type_breakdown": match_breakdown,
            "top_roas_asins": asin_perf,
        },
        "combined": {
            "total_revenue": round(total_revenue, 0),
            "organic_revenue": round(organic_rev, 0),
            "ad_attributed_revenue": round(total_attr, 0),
            "ad_contribution_pct": round(ad_contrib, 1),
            "organic_contribution_pct": round(100 - ad_contrib, 1),
            "overall_acos_pct": round(overall_acos, 1),
            "overall_roas": round(overall_roas, 2),
            "spend_to_revenue_pct": round(
                total_spend / total_revenue * 100 if total_revenue > 0 else 0, 1
            ),
        },
    }


# ── Main Agent Entry Point ────────────────────────────────────────────────────

async def run_agent(query: str,
                    sales_df: pd.DataFrame,
                    ad_df: pd.DataFrame) -> dict:
    """
    1. Build data summary from both CSVs
    2. Run rule-based tools for structured metrics
    3. Call AI with query + data → get structured JSON response
    4. Merge AI response with tool outputs and return
    """
    # Extract ASIN mention if any
    all_asins = list(sales_df["asin"].unique())
    mentioned_asin = next(
        (a for a in all_asins if a.upper() in query.upper()), None
    )

    # Build comprehensive data summary
    data_summary = build_data_summary(sales_df, ad_df, asin=mentioned_asin)

    # Also run rule-based tools for fallback metrics
    sales_result = sales_trend_analyzer(sales_df, asin=mentioned_asin)
    kw_result    = keyword_performance_evaluator(ad_df, asin=mentioned_asin)
    svr_result   = spend_vs_revenue_calculator(ad_df, sales_df, asin=mentioned_asin)
    tool_results = {
        "sales_trend":         sales_result,
        "keyword_performance": kw_result,
        "spend_vs_revenue":    svr_result,
    }
    rec_result = action_recommender(tool_results)

    # Build user prompt for AI
    user_prompt = (
        f'User Question: "{query}"\n\n'
        f"REAL DATA FROM THE SELLER'S ACCOUNT:\n"
        f"{json.dumps(data_summary, indent=2, ensure_ascii=True)}\n\n"
        f"Answer the user's specific question using ONLY this real data. "
        f"Include specific keyword names, ASIN codes, and exact amounts in your response."
    )

    # Call AI (Gemini or Groq based on .env)
    try:
        ai_response = await call_ai(user_prompt)
    except Exception as e:
        # Graceful fallback to rule-based if AI is unavailable
        ai_response = {
            "query_understanding": f"Rule-based analysis for: {query}",
            "analysis_steps": sales_result.get("analysis_steps", [
                "Parsed query intent",
                "Analyzed keyword performance",
                "Computed spend vs revenue",
                "Generated rule-based recommendations",
            ]),
            "key_findings": [
                f"Total Revenue: Rs.{data_summary['sales']['total_revenue']:,.0f}",
                f"Revenue Trend: {data_summary['sales']['trend']} ({data_summary['sales']['revenue_wow_change_pct']:+.1f}% WoW)",
                f"Overall ACoS: {data_summary['ads']['overall_acos_pct']}%",
                f"Overall ROAS: {data_summary['ads']['overall_roas']}x",
                f"Wasted Ad Spend: Rs.{data_summary['ads']['wasted_spend_estimate']:,.0f}",
                f"High-ACoS Keywords: {data_summary['ads']['high_acos_keyword_count']}",
                f"Zero-Conversion Keywords: {data_summary['ads']['zero_conversion_keyword_count']}",
                f"Ad vs Organic: {data_summary['combined']['ad_contribution_pct']}% / {data_summary['combined']['organic_contribution_pct']}%",
            ],
            "cross_dataset_insight": (
                f"AI provider unavailable ({e}). Rule-based insight: "
                f"Ad-attributed sales contribute {data_summary['combined']['ad_contribution_pct']}% of total revenue. "
                f"Overall ACoS is {data_summary['ads']['overall_acos_pct']}% with approximately "
                f"Rs.{data_summary['ads']['wasted_spend_estimate']:,.0f} in estimated wasted spend."
            ),
            "recommendations": rec_result.get("recommendations", []),
            "risk_warnings": rec_result.get("risk_warnings", []),
        }

    # Attach raw tool outputs for the what-if simulator
    ai_response["raw_tool_outputs"] = tool_results
    return ai_response