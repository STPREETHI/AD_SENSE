"""
Amazon Advertising & Sales Intelligence Agent — DEBUG & CLEAN v3.0
No bold, better debugging, simple prompt
"""

import json
import os
import re
import httpx
import pandas as pd
from typing import Optional, List, Dict, Any

from pydantic import BaseModel, Field, ValidationError

# ── Config ─────────────────────────────────────────────────────────────────────
AI_PROVIDER = os.getenv("AI_PROVIDER", "groq").lower()
GROQ_KEY = os.getenv("GROQ_API_KEY", "")
GEMINI_KEY = os.getenv("GEMINI_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


# ── Pydantic Schema ───────────────────────────────────────────────────────────
class Recommendation(BaseModel):
    action: str
    reason: str
    confidence: str = Field(..., pattern="^(High|Medium|Low)$")
    expected_impact: str


class AgentOutput(BaseModel):
    executive_summary: str
    query_understanding: str
    analysis_steps: List[str]
    key_findings: List[str]
    cross_dataset_insight: str
    recommendations: List[Recommendation]
    risk_warnings: List[str]


# ── SIMPLE SYSTEM PROMPT (No bold, no complications) ─────────────────────────
SYSTEM_PROMPT = """You are an elite Amazon Advertising Analyst.
Return ONLY valid JSON. No extra text, no markdown, no asterisks.

Use this exact structure:

{
  "executive_summary": "One clear sentence answering the question.",
  "query_understanding": "Short one-line understanding of the query.",
  "analysis_steps": ["Step 1", "Step 2", "Step 3"],
  "key_findings": [
    "Most Important: ...",
    "Critical Issue: ...",
    "Opportunity: ..."
  ],
  "cross_dataset_insight": "One powerful insight connecting sales and ads.",
  "recommendations": [
    {
      "action": "--> Your action here",
      "reason": "Why this action",
      "confidence": "High",
      "expected_impact": "Expected result"
    }
  ],
  "risk_warnings": ["Risk 1", "Risk 2"]
}
"""

# ── AI Call Functions ─────────────────────────────────────────────────────────
async def call_groq(user_prompt: str) -> str:
    if not GROQ_KEY:
        raise ValueError("GROQ_API_KEY is not set in .env")
    url = "https://api.groq.com/openai/v1/chat/completions"
    body = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.1,
        "max_tokens": 2200,
        "response_format": {"type": "json_object"},
    }
    headers = {"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"}
    
    async with httpx.AsyncClient(timeout=90) as client:
        r = await client.post(url, json=body, headers=headers)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]


async def call_gemini(user_prompt: str) -> str:
    if not GEMINI_KEY:
        raise ValueError("GEMINI_API_KEY is not set in .env")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_KEY}"
    body = {
        "contents": [{"role": "user", "parts": [{"text": f"{SYSTEM_PROMPT}\n\n{user_prompt}"}]}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 2200, "responseMimeType": "application/json"}
    }
    async with httpx.AsyncClient(timeout=90) as client:
        r = await client.post(url, json=body)
        r.raise_for_status()
        return r.json()["candidates"][0]["content"]["parts"][0]["text"]


def clean_output(raw: str) -> str:
    cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", raw).strip()
    match = re.search(r"(\{.*\})", cleaned, re.DOTALL)
    return match.group(1) if match else cleaned


# ── Data Summary ──────────────────────────────────────────────────────────────
def build_data_summary(sales_df: pd.DataFrame, ad_df: pd.DataFrame, asin: Optional[str] = None) -> dict:
    s = sales_df.copy()
    a = ad_df.copy()

    s["date"] = pd.to_datetime(s["date"])
    a["date"] = pd.to_datetime(a["date"])

    if asin:
        s = s[s["asin"] == asin]
        a = a[a["asin"] == asin]

    total_revenue = float(s["revenue"].sum())
    total_units = int(s["units_sold"].sum())

    top_products = (
        s.groupby(["asin", "product_title"])
         .agg(revenue=("revenue", "sum"), units=("units_sold", "sum"))
         .sort_values("revenue", ascending=False)
         .head(5)
         .assign(revenue=lambda x: x["revenue"].round(0).astype(int))
         .reset_index()
         .to_dict(orient="records")
    )

    total_spend = float(a["ad_spend"].sum())
    total_attr_sales = float(a["attributed_sales"].sum())

    overall_acos = (total_spend / total_attr_sales * 100) if total_attr_sales > 0 else 999.0
    overall_roas = (total_attr_sales / total_spend) if total_spend > 0 else 0.0
    ad_contribution_pct = round((total_attr_sales / total_revenue * 100) if total_revenue > 0 else 0, 1)

    return {
        "sales": {"total_revenue": round(total_revenue, 0), "total_units": total_units, "top_products": top_products},
        "ads": {"total_spend": round(total_spend, 0), "total_attributed_sales": round(total_attr_sales, 0),
                "overall_acos_pct": round(overall_acos, 1), "overall_roas": round(overall_roas, 2)},
        "combined": {"ad_contribution_pct": ad_contribution_pct}
    }


# ── Main Agent Function ───────────────────────────────────────────────────────
async def run_agent(query: str, sales_df: pd.DataFrame, ad_df: pd.DataFrame) -> dict:
    print(f"[DEBUG] Running agent for query: {query[:80]}...")   # ← Added for debugging

    try:
        mentioned_asin = next((a for a in sales_df["asin"].unique() if a.upper() in query.upper()), None)
        data_summary = build_data_summary(sales_df, ad_df, asin=mentioned_asin)

        user_prompt = f"""User Question: "{query}"

DATA SUMMARY:
{json.dumps(data_summary, indent=2, ensure_ascii=False)}

Analyze and return valid JSON only."""

        # Call AI
        if AI_PROVIDER == "groq":
            raw = await call_groq(user_prompt)
        else:
            raw = await call_gemini(user_prompt)

        cleaned = clean_output(raw)
        print(f"[DEBUG] Raw LLM response length: {len(cleaned)} chars")

        parsed_dict = json.loads(cleaned)
        validated = AgentOutput.model_validate(parsed_dict)

        print("[DEBUG] Agent succeeded")
        return validated.model_dump()

    except Exception as e:
        print(f"[ERROR] Agent failed: {type(e).__name__} - {e}")
        # Very clear fallback
        return {
            "executive_summary": "Analysis failed.",
            "query_understanding": "The system encountered an error while processing your request.",
            "analysis_steps": [],
            "key_findings": [f"Error: {str(e)[:150]}"],
            "cross_dataset_insight": "",
            "recommendations": [],
            "risk_warnings": ["Please check that data is loaded and backend is running."]
        }