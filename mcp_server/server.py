import json
import logging
import sys
from typing import Annotated

from mcp.server.mcpserver import MCPServer

from mcp_server.tools.sectors import (
    list_sectors as _list_sectors,
    get_sector_overview as _get_sector_overview,
)
from mcp_server.tools.companies import (
    list_companies as _list_companies,
    get_company_details as _get_company_details,
    compare_companies as _compare_companies,
)
from mcp_server.tools.financials import query_financials as _query_financials
from mcp_server.tools.news import search_news_events as _search_news_events

# > Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,  # MCP uses stdout for JSON-RPC, so logs go to stderr
)
logger = logging.getLogger("mcp_server")

# > Server instance
mcp = MCPServer(
    name="financial-analyst-tools",
    version="1.0.0",
    instructions=(
        "MCP tool server for the Financial Analyst Agent. "
        "Provides 7 tools to query a curated database of ~21 companies "
        "across 3 sectors (tech, retail, logistics): company profiles, "
        "financials, valuations, and news events."
    ),
)


# > Tool 1: list_sectors
@mcp.tool(
    description=(
        "Returns the list of available sectors with summary info. "
        "No parameters required. Returns name, display_name, overview, "
        "tailwinds, headwinds, and company_count for each sector."
    ),
)
def list_sectors() -> str:
    """Returns available sectors with overview info."""
    logger.info("Tool call: list_sectors()")
    result = _list_sectors()
    return json.dumps(result, indent=2)


# > Tool 2: get_sector_overview
@mcp.tool(
    description=(
        "Returns detailed overview for a specific sector, including "
        "dynamically computed aggregate metrics (avg P/E, avg EV/EBITDA, "
        "avg gross margin, avg revenue growth). "
        "Parameter: sector (string) — one of 'tech', 'retail', 'logistics'."
    ),
)
def get_sector_overview(sector: str) -> str:
    """Returns sector detail with dynamically computed aggregate metrics."""
    logger.info("Tool call: get_sector_overview(sector=%s)", sector)
    result = _get_sector_overview(sector)
    return json.dumps(result, indent=2)


# > Tool 3: list_companies
@mcp.tool(
    description=(
        "Returns all companies in a given sector with key identifiers and "
        "summary stats (market_cap, revenue). "
        "Parameters: sector (required, one of 'tech'/'retail'/'logistics'), "
        "sort_by (optional: 'market_cap', 'revenue', 'name'; default 'market_cap'), "
        "limit (optional int, default all)."
    ),
)
def list_companies(
    sector: str,
    sort_by: str = "market_cap",
    limit: int | None = None,
) -> str:
    """Returns companies in a sector with summary financials."""
    logger.info("Tool call: list_companies(sector=%s, sort_by=%s, limit=%s)", sector, sort_by, limit)
    result = _list_companies(sector, sort_by, limit)
    return json.dumps(result, indent=2)


# > Tool 4: get_company_details
@mcp.tool(
    description=(
        "Returns the full profile for a specific company by ticker symbol: "
        "company info (including headcount & hiring signals), all historical "
        "financials, latest valuation snapshot, and recent news events. "
        "Each financial and valuation record includes source and source_url "
        "for traceability. Returns an error if the ticker is not found."
    ),
)
def get_company_details(ticker: str) -> str:
    """Returns full company profile: financials + valuation + events."""
    logger.info("Tool call: get_company_details(ticker=%s)", ticker)
    result = _get_company_details(ticker)
    return json.dumps(result, indent=2)


# > Tool 5: compare_companies
@mcp.tool(
    description=(
        "Side-by-side comparison of 2 to 7 companies on key financial and "
        "valuation metrics. Uses most recent fiscal year for financials and "
        "most recent snapshot for valuations. "
        "Parameters: tickers (required, list of 2-7 ticker strings), "
        "metrics (optional list of metric names; default includes revenue, "
        "margins, EBITDA, FCF, debt-to-EBITDA, P/E, EV/EBITDA, market_cap). "
        "Reports any tickers not found in the database."
    ),
)
def compare_companies(
    tickers: list[str],
    metrics: list[str] | None = None,
) -> str:
    """Side-by-side comparison of companies on selected metrics."""
    logger.info("Tool call: compare_companies(tickers=%s, metrics=%s)", tickers, metrics)
    result = _compare_companies(tickers, metrics)
    return json.dumps(result, indent=2)


# > Tool 6: search_news_events
@mcp.tool(
    description=(
        "Search news and events for a company or across a sector. "
        "At least one of 'sector' or 'ticker' must be provided. "
        "Parameters: sector (optional), ticker (optional), "
        "event_type (optional: 'earnings', 'M&A', 'restructuring', 'hiring', "
        "'layoff', 'product_launch', 'guidance'), "
        "sentiment (optional: 'positive', 'negative', 'neutral'), "
        "limit (optional int, default 10)."
    ),
)
def search_news_events(
    sector: str | None = None,
    ticker: str | None = None,
    event_type: str | None = None,
    sentiment: str | None = None,
    limit: int = 10,
) -> str:
    """Search news and events by company, sector, type, or sentiment."""
    logger.info(
        "Tool call: search_news_events(sector=%s, ticker=%s, event_type=%s, sentiment=%s, limit=%s)",
        sector, ticker, event_type, sentiment, limit,
    )
    result = _search_news_events(sector, ticker, event_type, sentiment, limit)
    return json.dumps(result, indent=2)


# > Tool 7: query_financials
@mcp.tool(
    description=(
        "Rank or filter companies by a financial or valuation metric within "
        "a sector. Uses a strict whitelist to prevent SQL injection. "
        "Financial metrics: revenue, revenue_growth_pct, gross_margin_pct, "
        "operating_margin_pct, ebitda, free_cash_flow, total_debt, cash, "
        "debt_to_ebitda, eps, roe_pct. "
        "Valuation metrics: market_cap, enterprise_value, pe_ttm, pe_forward, "
        "ev_ebitda, dividend_yield. "
        "Parameters: sector (required), metric (required), "
        "order (optional: 'asc'/'desc', default 'desc'), "
        "min_value (optional float), max_value (optional float), "
        "limit (optional int, default 10)."
    ),
)
def query_financials(
    sector: str,
    metric: str,
    order: str = "desc",
    min_value: float | None = None,
    max_value: float | None = None,
    limit: int = 10,
) -> str:
    """Rank/filter companies by a financial or valuation metric."""
    logger.info(
        "Tool call: query_financials(sector=%s, metric=%s, order=%s, min=%s, max=%s, limit=%s)",
        sector, metric, order, min_value, max_value, limit,
    )
    result = _query_financials(sector, metric, order, min_value, max_value, limit)
    return json.dumps(result, indent=2)


# > Entry point
def main():
    """Run the MCP server over stdio transport."""
    logger.info("Starting Financial Analyst MCP Tool Server (stdio transport)...")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
