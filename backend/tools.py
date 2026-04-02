"""
Analytical tools for Amazon Advertising & Sales Intelligence Agent.
Each tool uses Pandas and returns a dict output.
"""

import pandas as pd
import numpy as np
from typing import Optional


def sales_trend_analyzer(df: pd.DataFrame, asin: Optional[str] = None, date_range: Optional[tuple] = None) -> dict:
    """
    Aggregates and compares sales across time periods.
    Returns trend metrics, week-over-week changes, and top/bottom performers.
    """
    d = df.copy()
    d["date"] = pd.to_datetime(d["date"])

    if asin:
        d = d[d["asin"] == asin]

    if date_range:
        start, end = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])
        d = d[(d["date"] >= start) & (d["date"] <= end)]

    if d.empty:
        return {"error": "No data found for given filters", "asin": asin}

    # Daily aggregation
    daily = d.groupby("date").agg(
        total_revenue=("revenue", "sum"),
        total_units=("units_sold", "sum"),
        avg_price=("selling_price", "mean"),
        avg_bsr=("bsr_rank", "mean"),
    ).reset_index()

    # Week-over-week split
    max_date = d["date"].max()
    split = max_date - pd.Timedelta(days=7)
    recent = d[d["date"] > split]
    prev = d[d["date"] <= split]

    recent_rev = recent["revenue"].sum()
    prev_rev = prev["revenue"].sum()
    wow_change = ((recent_rev - prev_rev) / prev_rev * 100) if prev_rev > 0 else 0

    recent_units = recent["units_sold"].sum()
    prev_units = prev["units_sold"].sum()
    units_wow = ((recent_units - prev_units) / prev_units * 100) if prev_units > 0 else 0

    # Top products
    top_products = (
        d.groupby(["asin", "product_title"])
        .agg(total_rev=("revenue", "sum"), total_units=("units_sold", "sum"))
        .sort_values("total_rev", ascending=False)
        .head(5)
        .reset_index()
        .to_dict(orient="records")
    )

    return {
        "tool": "sales_trend_analyzer",
        "asin_filter": asin,
        "total_revenue": round(float(d["revenue"].sum()), 2),
        "total_units_sold": int(d["units_sold"].sum()),
        "avg_daily_revenue": round(float(daily["total_revenue"].mean()), 2),
        "revenue_wow_change_pct": round(float(wow_change), 2),
        "units_wow_change_pct": round(float(units_wow), 2),
        "trend_direction": "up" if wow_change > 0 else ("down" if wow_change < -2 else "stable"),
        "top_products": top_products,
        "days_analyzed": int(len(daily)),
        "date_range": {
            "start": str(d["date"].min().date()),
            "end": str(d["date"].max().date()),
        },
    }


def keyword_performance_evaluator(ad_df: pd.DataFrame, asin: Optional[str] = None) -> dict:
    """
    Evaluates keyword performance:
    - Detects high ACoS (>70%)
    - Detects zero conversion keywords
    - Identifies top ROAS keywords
    """
    d = ad_df.copy()
    d["date"] = pd.to_datetime(d["date"])

    if asin:
        d = d[d["asin"] == asin]

    if d.empty:
        return {"error": "No ad data found", "asin": asin}

    # Aggregate by keyword
    kw = d.groupby(["asin", "keyword", "match_type"]).agg(
        total_impressions=("impressions", "sum"),
        total_clicks=("clicks", "sum"),
        total_spend=("ad_spend", "sum"),
        total_attributed_sales=("attributed_sales", "sum"),
        total_attributed_units=("attributed_units", "sum"),
        avg_cpc=("cpc", "mean"),
    ).reset_index()

    kw["acos"] = kw.apply(
        lambda r: (r["total_spend"] / r["total_attributed_sales"] * 100) if r["total_attributed_sales"] > 0 else 999,
        axis=1,
    )
    kw["ctr"] = kw.apply(
        lambda r: (r["total_clicks"] / r["total_impressions"] * 100) if r["total_impressions"] > 0 else 0,
        axis=1,
    )
    kw["cvr"] = kw.apply(
        lambda r: (r["total_attributed_units"] / r["total_clicks"] * 100) if r["total_clicks"] > 0 else 0,
        axis=1,
    )
    kw["roas"] = kw.apply(
        lambda r: (r["total_attributed_sales"] / r["total_spend"]) if r["total_spend"] > 0 else 0,
        axis=1,
    )

    # Classify keywords
    high_acos = kw[(kw["acos"] > 70) & (kw["total_spend"] > 0)].sort_values("total_spend", ascending=False)
    zero_conv = kw[(kw["total_clicks"] > 0) & (kw["total_attributed_units"] == 0)].sort_values("total_spend", ascending=False)
    top_roas = kw[kw["roas"] > 0].sort_values("roas", ascending=False).head(10)
    budget_burn = kw[kw["total_spend"] > 0].sort_values("total_spend", ascending=False).head(10)

    waste_spend = float(high_acos["total_spend"].sum()) + float(zero_conv["total_spend"].sum())

    def to_records(frame, cols):
        sub = frame[cols].head(10).copy()
        for c in sub.select_dtypes(include=[np.float64, np.int64]).columns:
            sub[c] = sub[c].round(2)
        return sub.to_dict(orient="records")

    cols_base = ["asin", "keyword", "match_type", "total_spend", "total_attributed_sales", "acos", "roas", "ctr", "cvr"]

    return {
        "tool": "keyword_performance_evaluator",
        "asin_filter": asin,
        "total_keywords_analyzed": int(len(kw)),
        "total_ad_spend": round(float(kw["total_spend"].sum()), 2),
        "total_attributed_sales": round(float(kw["total_attributed_sales"].sum()), 2),
        "overall_acos": round(
            float(kw["total_spend"].sum() / kw["total_attributed_sales"].sum() * 100)
            if kw["total_attributed_sales"].sum() > 0 else 999,
            2,
        ),
        "estimated_wasted_spend": round(waste_spend, 2),
        "high_acos_keywords": to_records(high_acos, cols_base),
        "zero_conversion_keywords": to_records(zero_conv, cols_base),
        "top_roas_keywords": to_records(top_roas, cols_base),
        "top_spend_keywords": to_records(budget_burn, cols_base),
        "high_acos_count": int(len(high_acos)),
        "zero_conv_count": int(len(zero_conv)),
    }


def spend_vs_revenue_calculator(ad_df: pd.DataFrame, sales_df: pd.DataFrame, asin: Optional[str] = None) -> dict:
    """
    Connects ad spend to actual sales impact.
    Identifies organic vs ad-attributed contribution and ROI.
    """
    ad = ad_df.copy()
    sales = sales_df.copy()
    ad["date"] = pd.to_datetime(ad["date"])
    sales["date"] = pd.to_datetime(sales["date"])

    if asin:
        ad = ad[ad["asin"] == asin]
        sales = sales[sales["asin"] == asin]

    # Aggregate ad data by date
    daily_ad = ad.groupby("date").agg(
        total_spend=("ad_spend", "sum"),
        attributed_sales=("attributed_sales", "sum"),
        attributed_units=("attributed_units", "sum"),
    ).reset_index()

    # Aggregate sales by date
    daily_sales = sales.groupby("date").agg(
        total_revenue=("revenue", "sum"),
        total_units=("units_sold", "sum"),
    ).reset_index()

    # Merge
    merged = pd.merge(daily_sales, daily_ad, on="date", how="left").fillna(0)
    merged["organic_revenue"] = merged["total_revenue"] - merged["attributed_sales"].clip(upper=merged["total_revenue"])
    merged["organic_units"] = merged["total_units"] - merged["attributed_units"].clip(upper=merged["total_units"])
    merged["ad_contribution_pct"] = merged.apply(
        lambda r: (r["attributed_sales"] / r["total_revenue"] * 100) if r["total_revenue"] > 0 else 0, axis=1
    )

    total_rev = float(merged["total_revenue"].sum())
    total_ad_sales = float(merged["attributed_sales"].sum())
    total_spend = float(merged["total_spend"].sum())
    total_organic = float(merged["organic_revenue"].sum())

    overall_acos = (total_spend / total_ad_sales * 100) if total_ad_sales > 0 else 999
    overall_roi = ((total_ad_sales - total_spend) / total_spend * 100) if total_spend > 0 else 0
    ad_contribution = (total_ad_sales / total_rev * 100) if total_rev > 0 else 0

    # Correlation between spend and sales (Pearson)
    corr = merged["total_spend"].corr(merged["total_revenue"]) if len(merged) > 2 else 0

    # Scenario: 20% spend reduction impact
    simulated_spend = total_spend * 0.8
    simulated_attributed = total_ad_sales * 0.85  # assuming ~15% drop in attributed
    simulated_total = total_organic + simulated_attributed

    return {
        "tool": "spend_vs_revenue_calculator",
        "asin_filter": asin,
        "total_revenue": round(total_rev, 2),
        "total_ad_spend": round(total_spend, 2),
        "total_attributed_sales": round(total_ad_sales, 2),
        "total_organic_revenue": round(total_organic, 2),
        "ad_contribution_pct": round(ad_contribution, 2),
        "organic_contribution_pct": round(100 - ad_contribution, 2),
        "overall_acos": round(overall_acos, 2),
        "overall_roi_pct": round(overall_roi, 2),
        "spend_sales_correlation": round(float(corr), 3),
        "interpretation": (
            "Strong ad dependency" if ad_contribution > 60
            else "Organic dominant" if ad_contribution < 30
            else "Balanced ad-organic mix"
        ),
        "what_if_20pct_cut": {
            "current_spend": round(total_spend, 2),
            "reduced_spend": round(simulated_spend, 2),
            "estimated_revenue_impact": round(simulated_total, 2),
            "estimated_savings": round(total_spend - simulated_spend, 2),
        },
    }


def action_recommender(results: dict) -> dict:
    """
    Synthesizes results from all tools and generates prioritized recommendations.
    """
    recommendations = []
    risk_warnings = []

    kw = results.get("keyword_performance", {})
    svr = results.get("spend_vs_revenue", {})
    trend = results.get("sales_trend", {})

    # Rule 1: High wasted spend
    wasted = kw.get("estimated_wasted_spend", 0)
    if wasted > 500:
        recommendations.append({
            "action": f"Pause or reduce bids on {kw.get('high_acos_count', 0)} high-ACoS keywords",
            "reason": f"Estimated ₹{wasted:,.0f} in wasted ad spend on keywords with ACoS >70% or zero conversions",
            "confidence": "High",
            "expected_impact": "Immediate cost reduction without significant revenue loss",
        })

    # Rule 2: Zero-conversion keywords
    zero_count = kw.get("zero_conv_count", 0)
    if zero_count > 5:
        recommendations.append({
            "action": f"Pause {zero_count} zero-conversion keywords immediately",
            "reason": "These keywords are generating clicks but zero attributed sales — pure budget drain",
            "confidence": "High",
            "expected_impact": "Reduce ACoS and free up budget for profitable keywords",
        })

    # Rule 3: Organic dominance — reduce ad reliance
    organic_pct = svr.get("organic_contribution_pct", 0)
    if organic_pct > 70:
        recommendations.append({
            "action": "Reduce overall ad budget by 15-20%",
            "reason": f"Organic sales contribute {organic_pct:.0f}% of revenue — ads are supplementary, not critical",
            "confidence": "Medium",
            "expected_impact": "Cost savings with minimal revenue impact; reinvest in SEO/listing optimization",
        })

    # Rule 4: High ad dependency + declining sales
    ad_dep = svr.get("ad_contribution_pct", 0)
    trend_dir = trend.get("trend_direction", "stable")
    if ad_dep > 60 and trend_dir == "down":
        recommendations.append({
            "action": "Investigate listing quality and pricing — do not cut ads yet",
            "reason": "Sales are declining despite high ad dependency; cutting ads would accelerate the drop",
            "confidence": "High",
            "expected_impact": "Stabilize revenue while root cause is identified",
        })
        risk_warnings.append("⚠️ Sales declining with high ad dependency — potential demand or listing issue")

    # Rule 5: What-if simulation
    what_if = svr.get("what_if_20pct_cut", {})
    savings = what_if.get("estimated_savings", 0)
    if savings > 0:
        recommendations.append({
            "action": "Run 20% spend reduction test on bottom-performing ad groups",
            "reason": f"Simulation shows ₹{savings:,.0f} potential savings with minimal revenue impact",
            "confidence": "Medium",
            "expected_impact": "Improved ROAS and margin; validate with 2-week A/B test",
        })

    # Rule 6: Overall ACoS alert
    overall_acos = kw.get("overall_acos", 0)
    if overall_acos > 50:
        risk_warnings.append(f"🚨 Overall ACoS is {overall_acos:.1f}% — significantly above healthy threshold of 30%")
        recommendations.append({
            "action": "Audit all match types — shift budget from BROAD to EXACT match",
            "reason": f"High overall ACoS ({overall_acos:.1f}%) suggests poor keyword targeting precision",
            "confidence": "High",
            "expected_impact": "Reduce wasted impressions and improve conversion rate",
        })

    # Rule 7: WoW revenue drop
    wow = trend.get("revenue_wow_change_pct", 0)
    if wow < -15:
        risk_warnings.append(f"📉 Revenue dropped {abs(wow):.1f}% week-over-week — requires immediate investigation")

    if not recommendations:
        recommendations.append({
            "action": "Maintain current strategy with weekly monitoring",
            "reason": "Performance metrics are within acceptable ranges",
            "confidence": "Medium",
            "expected_impact": "Stable performance; continue to optimize incrementally",
        })

    return {
        "tool": "action_recommender",
        "recommendations": recommendations,
        "risk_warnings": risk_warnings,
        "priority_score": len([r for r in recommendations if r["confidence"] == "High"]),
    }
