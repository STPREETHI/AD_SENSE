from pydantic import BaseModel
from typing import List, Optional, Any, Dict


class QueryRequest(BaseModel):
    query: str
    asin: Optional[str] = None


class Recommendation(BaseModel):
    action: str
    reason: str
    confidence: str
    expected_impact: str


class AgentResponse(BaseModel):
    query_understanding: str
    analysis_steps: List[str]
    key_findings: List[str]
    cross_dataset_insight: str
    recommendations: List[Recommendation]
    risk_warnings: List[str]
    raw_tool_outputs: Optional[Dict[str, Any]] = None


class MetricsResponse(BaseModel):
    total_revenue: float
    total_ad_spend: float
    total_profit: float
    overall_acos: float
    total_units_sold: int
    total_attributed_sales: float
    organic_revenue: float
    ad_contribution_pct: float
    top_asins: List[Dict[str, Any]]
    daily_trend: List[Dict[str, Any]]
    spend_trend: List[Dict[str, Any]]
