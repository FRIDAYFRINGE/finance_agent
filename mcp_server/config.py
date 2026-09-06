from pathlib import Path

# > Database path — resolved relative to project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "financial_agent.db"

# > Valid sector names (must match sectors.name in the DB)
VALID_SECTORS = {"tech", "retail", "logistics"}

# > Metric whitelists — maps user-facing metric name → (table, column)
# This is the SQL-injection prevention layer: only whitelisted names are
# allowed in ORDER BY / WHERE clauses.  No raw user input ever reaches SQL.
FINANCIAL_METRICS: dict[str, str] = {
    "revenue":              "revenue",
    "revenue_growth_pct":   "revenue_growth_pct",
    "net_income":           "net_income",
    "gross_margin_pct":     "gross_margin_pct",
    "operating_margin_pct": "operating_margin_pct",
    "ebitda":               "ebitda",
    "free_cash_flow":       "free_cash_flow",
    "total_debt":           "total_debt",
    "cash":                 "cash",
    "debt_to_ebitda":       "debt_to_ebitda",
    "eps":                  "eps",
    "roe_pct":              "roe_pct",
}

VALUATION_METRICS: dict[str, str] = {
    "market_cap":        "market_cap",
    "enterprise_value":  "enterprise_value",
    "pe_ttm":            "pe_ttm",
    "pe_forward":        "pe_forward",
    "ev_ebitda":         "ev_ebitda",
    "price":             "price",
    "dividend_yield":    "dividend_yield",
}

# > Combined lookup: metric_name → ("financials" | "valuations", column_name)
METRIC_TABLE_MAP: dict[str, tuple[str, str]] = {}
for name, col in FINANCIAL_METRICS.items():
    METRIC_TABLE_MAP[name] = ("financials", col)
for name, col in VALUATION_METRICS.items():
    METRIC_TABLE_MAP[name] = ("valuations", col)

ALL_METRIC_NAMES = sorted(METRIC_TABLE_MAP.keys())

# > Valid sort options for list_companies
VALID_SORT_OPTIONS = {"market_cap", "revenue", "name"}

# > Default comparison metrics (compare_companies)
DEFAULT_COMPARE_METRICS = [
    "revenue", "gross_margin_pct", "operating_margin_pct", "ebitda",
    "free_cash_flow", "debt_to_ebitda", "pe_ttm", "ev_ebitda", "market_cap",
]

# > Valid event types and sentiments (news_events)
VALID_EVENT_TYPES = {
    "earnings", "M&A", "restructuring", "hiring",
    "layoff", "product_launch", "guidance",
}

VALID_SENTIMENTS = {"positive", "negative", "neutral"}
