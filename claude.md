# Amazon Advertising & Sales Intelligence Agent — claude.md

## 1. Project Overview

A fully local, agentic AI system that acts as an intelligent advertising & sales analyst for Amazon sellers. It accepts natural language queries, reasons over two datasets (Sales + Keyword Ads), calls analytical tools, performs cross-dataset reasoning, and returns structured business insights with actionable recommendations.

No paid APIs required. Runs entirely on your machine using Ollama (llama3).

---

## 2. Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                        FRONTEND                             │
│  index.html + styles.css + script.js                        │
│  ┌──────────┐ ┌─────────────┐ ┌───────────────────────┐    │
│  │ Upload   │ │ KPI Cards + │ │   AI Agent Chat UI    │    │
│  │ CSV Files│ │ Charts      │ │   What-If Simulator   │    │
│  └────┬─────┘ └──────┬──────┘ └──────────┬────────────┘    │
└───────┼──────────────┼───────────────────┼─────────────────┘
        │  HTTP        │  GET /metrics     │  POST /query
        │  POST /upload│                   │
┌───────▼──────────────▼───────────────────▼─────────────────┐
│                    FASTAPI BACKEND (main.py)                │
│  /upload → load CSVs into memory                           │
│  /metrics → aggregate KPIs for dashboard                   │
│  /query  → invoke agent                                     │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                     AGENT (agent.py)                        │
│  1. call_ollama(query) → parse intent & generate plan       │
│  2. extract_asin_from_query() → filter if ASIN mentioned    │
│  3. Run analytical tools                                    │
│  4. synthesize_with_llm() → cross-dataset narrative         │
│  5. Return structured JSON                                   │
└──────┬──────────────┬──────────────┬────────────────────────┘
       │              │              │
┌──────▼─────┐ ┌──────▼─────┐ ┌─────▼──────────┐
│ sales_trend│ │ keyword_   │ │ spend_vs_      │
│ _analyzer  │ │ performance│ │ revenue_       │
│            │ │ _evaluator │ │ calculator     │
└──────┬─────┘ └──────┬─────┘ └─────┬──────────┘
       └──────────────┴─────────────┘
                      │
              ┌───────▼──────┐
              │ action_      │
              │ recommender  │
              └──────────────┘
                      │
              ┌───────▼──────┐
              │ Ollama LLM   │
              │ (llama3)     │
              └──────────────┘
```

---

## 3. Agent Workflow

```
User Query
    │
    ▼
[Step 1] parse_query_with_llm()
    → LLM identifies intent, focus, ASIN, time range
    → Generates analysis_steps list
    │
    ▼
[Step 2] extract_asin_from_query()
    → Checks if a specific ASIN appears in the query
    │
    ▼
[Step 3] Tool Execution (parallel conceptually)
    ├── sales_trend_analyzer(sales_df, asin, date_range)
    ├── keyword_performance_evaluator(ad_df, asin)
    └── spend_vs_revenue_calculator(ad_df, sales_df, asin)
    │
    ▼
[Step 4] action_recommender(tool_results)
    → Applies cross-dataset rules
    → Generates prioritized recommendations + risk warnings
    │
    ▼
[Step 5] synthesize_with_llm(query, tool_results)
    → LLM writes a natural language cross-dataset insight
    │
    ▼
[Output] Structured JSON response
```

---

## 4. Tool Explanations

### `sales_trend_analyzer(df, asin, date_range)`
- Aggregates revenue, units sold, BSR by date
- Computes week-over-week (WoW) revenue and units change
- Identifies trend direction (up / down / stable)
- Lists top 5 products by revenue
- **Returns:** trend direction, WoW change %, top products, date range

### `keyword_performance_evaluator(ad_df, asin)`
- Groups by keyword + match_type
- Calculates ACoS, CTR, CVR, ROAS per keyword
- Flags high-ACoS keywords (>70%)
- Flags zero-conversion keywords (clicks > 0, units = 0)
- Estimates wasted spend
- **Returns:** keyword classifications, wasted spend, overall ACoS

### `spend_vs_revenue_calculator(ad_df, sales_df, asin)`
- Merges daily ad data with daily sales data
- Calculates ad-attributed vs organic contribution
- Computes overall ROI and Pearson correlation (spend ↔ revenue)
- Runs What-If simulation for spend reduction
- **Returns:** ad/organic split, ROI, correlation, simulation

### `action_recommender(results)`
- Pure rule-based engine using outputs from all 3 tools
- Rules: high wasted spend → pause keywords; organic dominant → reduce budget; high ad dependency + declining sales → don't cut ads; etc.
- **Returns:** prioritized recommendations with confidence + expected impact

---

## 5. Setup Steps

### Prerequisites
- Python 3.10+
- Node not required (pure HTML frontend)

### Step 1: Clone / download the project
```bash
cd project/
```

### Step 2: Install Python dependencies
```bash
pip install -r requirements.txt
```

### Step 3: Install Ollama
Visit https://ollama.com and install for your OS.

### Step 4: Pull the LLM model
```bash
ollama pull llama3
```
> Note: If llama3 is not available, use `ollama pull mistral`
> Then update `OLLAMA_MODEL = "mistral"` in `backend/agent.py`

### Step 5: Start the backend
```bash
cd backend/
uvicorn main:app --reload --port 8000
```

### Step 6: Open the frontend
```bash
# Simply open in browser:
open frontend/index.html
# or on Linux:
xdg-open frontend/index.html
```

### Step 7: Upload data or use defaults
- The system auto-loads CSVs from the `data/` directory on startup
- Or use the Upload panel in the UI to load your own CSVs

---

## 6. API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET    | `/`       | Health check, data status |
| POST   | `/upload` | Upload sales.csv + ads.csv |
| POST   | `/query`  | Run agent on natural language query |
| GET    | `/metrics`| Return dashboard KPIs + chart data |
| GET    | `/asins`  | List all available ASINs |

### POST /query — Request Body
```json
{
  "query": "Which keywords are burning my budget?",
  "asin": "B09L4ZTM2V"  // optional
}
```

### POST /query — Response Schema
```json
{
  "query_understanding": "...",
  "analysis_steps": ["step1", "step2"],
  "key_findings": ["finding1", "finding2"],
  "cross_dataset_insight": "...",
  "recommendations": [
    {
      "action": "...",
      "reason": "...",
      "confidence": "High|Medium|Low",
      "expected_impact": "..."
    }
  ],
  "risk_warnings": ["..."],
  "raw_tool_outputs": { ... }
}
```

---

## 7. Example Queries

```
1. "Which keywords are eating my budget without converting?"
   → Triggers keyword_performance_evaluator, identifies zero-conversion + high-ACoS keywords

2. "My sales dropped last week on B09L4ZTM2V — is it an ad issue or organic?"
   → Filters by ASIN, compares WoW trend + ad spend stability

3. "Give me a plan to cut ad waste by 20% without hurting sales"
   → Runs spend_vs_revenue_calculator what-if + action_recommender

4. "What's my best performing campaign and why?"
   → Runs keyword_performance_evaluator, ranks by ROAS

5. "Show full audit of all products"
   → Runs all tools across all ASINs, comprehensive report

6. "Which products are organically strong and don't need ad support?"
   → spend_vs_revenue_calculator identifies high organic contribution ASINs
```

---

## 8. Limitations

- **Ollama must be running locally** — if offline, the system falls back to rule-based responses (no LLM narrative)
- **No real-time data** — requires manual CSV upload; no Amazon SP-API integration
- **Profit margin** — calculated from `profit_margin_pct` column if present; otherwise estimated from revenue - ad spend (approximate)
- **Cross-ASIN ad attribution** — the system assumes `attributed_sales` in ad data corresponds to the same ASIN's `revenue` in sales data
- **Date alignment** — WoW calculations require at least 14 days of data for meaningful comparison
- **LLM quality** — llama3 8B has limited context; very large datasets may produce generic insights
- **Concurrency** — single in-memory data store; not suitable for multi-user production use

---

## 9. Future Scope

1. **Amazon SP-API Integration** — Pull live data instead of CSV uploads
2. **Automated bidding suggestions** — Calculate exact bid values based on target ACoS
3. **Product lifecycle detection** — Identify launch vs mature vs declining ASINs
4. **Dayparting analysis** — Analyze performance by hour/day of week
5. **Competitor tracking** — BSR trend vs ad spend correlation
6. **Email/Slack alerts** — Automated daily digest of high-risk keywords
7. **Multi-user support** — PostgreSQL backend + user authentication
8. **Vector memory** — Store past analyses; agent remembers historical patterns
9. **Fine-tuned model** — Domain-specific LLM trained on Amazon seller data
10. **Campaign-level grouping** — Group keywords by campaign/ad group for portfolio analysis
