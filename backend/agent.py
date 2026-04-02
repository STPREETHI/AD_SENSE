"""
Amazon Advertising & Sales Intelligence Agent.
Uses Ollama (llama3) for query understanding and planning,
then calls analytical tools and performs cross-dataset reasoning.
"""

import json
import re
import requests
from typing import Optional
import pandas as pd

from tools import (
    sales_trend_analyzer,
    keyword_performance_evaluator,
    spend_vs_revenue_calculator,
    action_recommender,
)

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3"


def call_ollama(prompt: str, system: str = "") -> str:
    """Call local Ollama LLM."""
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "system": system,
        "stream": False,
        "options": {"temperature": 0.2, "num_predict": 800},
    }
    try:
        resp = requests.post(OLLAMA_URL, json=payload, timeout=60)
        resp.raise_for_status()
        return resp.json().get("response", "")
    except Exception as e:
        return f"[LLM unavailable: {str(e)}] Proceeding with rule-based analysis."


def extract_asin_from_query(query: str, available_asins: list) -> Optional[str]:
    """Extract ASIN from query if mentioned."""
    query_upper = query.upper()
    for asin in available_asins:
        if asin.upper() in query_upper:
            return asin
    return None


def parse_query_with_llm(query: str) -> dict:
    """Use LLM to understand query intent and generate analysis plan."""
    system = """You are an Amazon advertising analyst AI. 
Analyze the user's query and return ONLY a JSON object with these fields:
{
  "intent": "one of: keyword_analysis|sales_trend|spend_efficiency|full_audit|what_if|comparison",
  "focus": "keywords|products|both",
  "asin_mentioned": "ASIN string or null",
  "time_focus": "recent|specific|all",
  "analysis_steps": ["step1", "step2", "step3"],
  "summary": "one sentence description of what to analyze"
}
Return ONLY valid JSON, no other text."""

    response = call_ollama(query, system=system)

    # Try to parse JSON from LLM response
    try:
        # Find JSON in response
        match = re.search(r"\{.*\}", response, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception:
        pass

    # Fallback: rule-based parsing
    query_lower = query.lower()
    intent = "full_audit"
    if any(w in query_lower for w in ["keyword", "acos", "converting", "conversion", "burn"]):
        intent = "keyword_analysis"
    elif any(w in query_lower for w in ["sales", "revenue", "dropped", "trend", "organic"]):
        intent = "sales_trend"
    elif any(w in query_lower for w in ["spend", "budget", "waste", "roi", "roas"]):
        intent = "spend_efficiency"
    elif any(w in query_lower for w in ["cut", "reduce", "20%", "plan"]):
        intent = "what_if"

    return {
        "intent": intent,
        "focus": "both",
        "asin_mentioned": None,
        "time_focus": "all",
        "analysis_steps": [
            "Analyze keyword performance and identify waste",
            "Review sales trends and week-over-week changes",
            "Calculate spend vs revenue and organic contribution",
            "Generate prioritized recommendations",
        ],
        "summary": f"Performing {intent} analysis across all products",
    }


def synthesize_with_llm(query: str, tool_results: dict, plan: dict) -> dict:
    """Use LLM to synthesize findings into a narrative insight."""
    # Prepare compact summary for LLM
    summary = {
        "sales_trend": {
            "total_revenue": tool_results.get("sales_trend", {}).get("total_revenue"),
            "wow_change": tool_results.get("sales_trend", {}).get("revenue_wow_change_pct"),
            "trend": tool_results.get("sales_trend", {}).get("trend_direction"),
        },
        "keyword_perf": {
            "overall_acos": tool_results.get("keyword_performance", {}).get("overall_acos"),
            "wasted_spend": tool_results.get("keyword_performance", {}).get("estimated_wasted_spend"),
            "high_acos_count": tool_results.get("keyword_performance", {}).get("high_acos_count"),
            "zero_conv_count": tool_results.get("keyword_performance", {}).get("zero_conv_count"),
        },
        "spend_vs_revenue": {
            "ad_contribution_pct": tool_results.get("spend_vs_revenue", {}).get("ad_contribution_pct"),
            "organic_pct": tool_results.get("spend_vs_revenue", {}).get("organic_contribution_pct"),
            "overall_roi": tool_results.get("spend_vs_revenue", {}).get("overall_roi_pct"),
        },
    }

    system = """You are an Amazon advertising expert. 
Given analytical results, write a cross-dataset insight paragraph in plain English.
Focus on connecting ad performance to sales outcomes.
Be specific with numbers. Keep it under 150 words.
Return ONLY the insight text, no JSON."""

    prompt = f"""
User query: {query}

Analysis results: {json.dumps(summary, indent=2)}

Write a cross-dataset business insight connecting these findings.
"""

    insight = call_ollama(prompt, system=system)

    # Fallback insight if LLM unavailable
    if "[LLM unavailable" in insight or not insight.strip():
        ad_pct = summary["spend_vs_revenue"].get("ad_contribution_pct", 0) or 0
        wow = summary["sales_trend"].get("wow_change", 0) or 0
        acos = summary["keyword_perf"].get("overall_acos", 0) or 0
        waste = summary["keyword_perf"].get("wasted_spend", 0) or 0

        insight = (
            f"Ad-attributed sales contribute {ad_pct:.1f}% of total revenue, "
            f"with organic driving the remaining {100 - ad_pct:.1f}%. "
            f"Overall ACoS stands at {acos:.1f}%, "
            f"with an estimated ₹{waste:,.0f} in wasted spend on non-converting keywords. "
            f"Week-over-week revenue has {'grown' if wow > 0 else 'declined'} by {abs(wow):.1f}%. "
            f"Cross-referencing both datasets suggests the primary optimization opportunity lies in "
            f"keyword-level bid management rather than overall budget changes."
        )

    return {"cross_dataset_insight": insight.strip()}


def run_agent(query: str, sales_df: pd.DataFrame, ad_df: pd.DataFrame) -> dict:
    """
    Main agent entry point.
    1. Parse query → plan
    2. Call tools
    3. Cross-dataset reasoning
    4. Return structured JSON
    """
    # Step 1: Understand query
    plan = parse_query_with_llm(query)

    # Extract ASIN if mentioned
    available_asins = list(sales_df["asin"].unique())
    asin_filter = plan.get("asin_mentioned") or extract_asin_from_query(query, available_asins)

    analysis_steps = plan.get(
        "analysis_steps",
        [
            "Parse query intent",
            "Analyze sales trends",
            "Evaluate keyword performance",
            "Calculate spend vs revenue",
            "Generate recommendations",
        ],
    )

    # Step 2: Run all tools
    sales_result = sales_trend_analyzer(sales_df, asin=asin_filter)
    kw_result = keyword_performance_evaluator(ad_df, asin=asin_filter)
    svr_result = spend_vs_revenue_calculator(ad_df, sales_df, asin=asin_filter)

    tool_results = {
        "sales_trend": sales_result,
        "keyword_performance": kw_result,
        "spend_vs_revenue": svr_result,
    }

    # Step 3: Action recommendations
    rec_result = action_recommender(tool_results)

    # Step 4: LLM synthesis
    synthesis = synthesize_with_llm(query, tool_results, plan)

    # Step 5: Build final response
    return {
        "query_understanding": plan.get("summary", query),
        "analysis_steps": analysis_steps,
        "key_findings": [
            f"Total Revenue: ₹{sales_result.get('total_revenue', 0):,.2f}",
            f"Revenue Trend: {sales_result.get('trend_direction', 'N/A').upper()} "
            f"({sales_result.get('revenue_wow_change_pct', 0):+.1f}% WoW)",
            f"Overall ACoS: {kw_result.get('overall_acos', 0):.1f}%",
            f"Wasted Ad Spend: ₹{kw_result.get('estimated_wasted_spend', 0):,.2f}",
            f"High-ACoS Keywords: {kw_result.get('high_acos_count', 0)}",
            f"Zero-Conversion Keywords: {kw_result.get('zero_conv_count', 0)}",
            f"Ad vs Organic Split: {svr_result.get('ad_contribution_pct', 0):.1f}% / "
            f"{svr_result.get('organic_contribution_pct', 0):.1f}%",
            f"Ad ROI: {svr_result.get('overall_roi_pct', 0):.1f}%",
        ],
        "cross_dataset_insight": synthesis["cross_dataset_insight"],
        "recommendations": rec_result["recommendations"],
        "risk_warnings": rec_result["risk_warnings"],
        "raw_tool_outputs": tool_results,
    }
