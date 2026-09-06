"""Company-related MCP tools: list_companies, get_company_details, compare_companies.

These tools query the `companies` table and join across `financials`,
`valuations`, and `news_events` as needed.
"""

from mcp_server.db import get_connection, rows_to_list, row_to_dict
from mcp_server.config import (
    VALID_SECTORS,
    VALID_SORT_OPTIONS,
    DEFAULT_COMPARE_METRICS,
    METRIC_TABLE_MAP,
    ALL_METRIC_NAMES,
)


def list_companies(
    sector: str,
    sort_by: str = "market_cap",
    limit: int | None = None,
) -> list[dict]:
    """Returns all companies in a sector with key identifiers and summary stats.

    Args:
        sector: One of 'tech', 'retail', 'logistics'.
        sort_by: Sort by 'market_cap', 'revenue', or 'name'. Default: 'market_cap'.
        limit: Maximum number of results. Default: all.

    Returns:
        List of dicts with: ticker, name, sector, sub_sector, description,
        market_cap (latest valuation), revenue (latest financials).
    """
    sector = sector.strip().lower()
    if sector not in VALID_SECTORS:
        return [{"error": f"Invalid sector '{sector}'. Must be one of: {', '.join(sorted(VALID_SECTORS))}"}]

    if sort_by not in VALID_SORT_OPTIONS:
        sort_by = "market_cap"

    # Map sort_by to SQL ORDER BY clause
    sort_map = {
        "market_cap": "v.market_cap DESC",
        "revenue": "f.revenue DESC",
        "name": "c.name ASC",
    }
    order_clause = sort_map[sort_by]

    query = f"""
        SELECT
            c.ticker,
            c.name,
            s.name AS sector,
            c.sub_sector,
            c.description,
            v.market_cap,
            f.revenue
        FROM companies c
        JOIN sectors s ON c.sector_id = s.id
        LEFT JOIN valuations v ON v.company_id = c.id
        LEFT JOIN financials f ON f.company_id = c.id
            AND f.fiscal_year = (
                SELECT MAX(f2.fiscal_year)
                FROM financials f2
                WHERE f2.company_id = c.id
            )
        WHERE s.name = ?
        ORDER BY {order_clause}
    """

    params: list = [sector]
    if limit is not None and limit > 0:
        query += " LIMIT ?"
        params.append(limit)

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(query, params)
        return rows_to_list(cur.fetchall())
    finally:
        conn.close()


def get_company_details(ticker: str) -> dict:
    """Returns full profile for a company: profile + financials + valuation + recent events.

    Args:
        ticker: Company ticker symbol (e.g. 'NVDA', 'FDX').

    Returns:
        Dict with keys: company, financials, valuation, recent_events.
        If ticker not found: {"error": "Company not found", "ticker": "..."}
    """
    ticker = ticker.strip().upper()
    conn = get_connection()
    try:
        cur = conn.cursor()

        # --- Company profile ---
        cur.execute("""
            SELECT
                c.ticker, c.name,
                s.name AS sector,
                c.sub_sector, c.description,
                c.headcount, c.headcount_change_pct,
                c.data_as_of
            FROM companies c
            JOIN sectors s ON c.sector_id = s.id
            WHERE c.ticker = ?
        """, (ticker,))
        company_row = cur.fetchone()
        if not company_row:
            return {"error": "Company not found", "ticker": ticker}

        company = row_to_dict(company_row)

        # --- Financials (all years, ordered newest first) ---
        cur.execute("""
            SELECT
                fiscal_year, revenue, revenue_growth_pct, net_income,
                gross_margin_pct, operating_margin_pct, ebitda, free_cash_flow,
                total_debt, cash, debt_to_ebitda, eps, roe_pct,
                source, source_url
            FROM financials
            WHERE company_id = (SELECT id FROM companies WHERE ticker = ?)
            ORDER BY fiscal_year DESC
        """, (ticker,))
        financials = rows_to_list(cur.fetchall())

        # --- Valuation (most recent snapshot) ---
        cur.execute("""
            SELECT
                as_of_date, market_cap, enterprise_value,
                pe_ttm, pe_forward, ev_ebitda, price, dividend_yield,
                source, source_url
            FROM valuations
            WHERE company_id = (SELECT id FROM companies WHERE ticker = ?)
            ORDER BY as_of_date DESC
            LIMIT 1
        """, (ticker,))
        val_row = cur.fetchone()
        valuation = row_to_dict(val_row) if val_row else None

        # --- Recent events (ordered by date, newest first) ---
        cur.execute("""
            SELECT
                event_date, event_type, headline, summary, sentiment, source_url
            FROM news_events
            WHERE company_id = (SELECT id FROM companies WHERE ticker = ?)
            ORDER BY event_date DESC
        """, (ticker,))
        recent_events = rows_to_list(cur.fetchall())

        return {
            "company": company,
            "financials": financials,
            "valuation": valuation,
            "recent_events": recent_events,
        }

    finally:
        conn.close()


def compare_companies(
    tickers: list[str],
    metrics: list[str] | None = None,
) -> list[dict] | dict:
    """Side-by-side comparison of 2+ companies on key financial and valuation metrics.

    Args:
        tickers: List of ticker symbols (2–7).
        metrics: Specific metrics to compare. Defaults to a comprehensive set.

    Returns:
        List of dicts, one per company, with: ticker, name, and each
        requested metric with its value.
        Or error dict if validation fails.
    """
    if not tickers or len(tickers) < 2:
        return {"error": "Provide at least 2 tickers to compare."}
    if len(tickers) > 7:
        return {"error": "Maximum 7 tickers for comparison."}

    # Normalise tickers
    tickers = [t.strip().upper() for t in tickers]

    # Determine metrics to use
    if metrics is None:
        metrics = DEFAULT_COMPARE_METRICS
    else:
        # Validate metrics against whitelist
        invalid = [m for m in metrics if m not in METRIC_TABLE_MAP]
        if invalid:
            return {
                "error": f"Unknown metric(s): {', '.join(invalid)}. "
                         f"Allowed: {', '.join(ALL_METRIC_NAMES)}"
            }

    conn = get_connection()
    try:
        cur = conn.cursor()

        # Check which tickers exist
        placeholders = ",".join("?" for _ in tickers)
        cur.execute(
            f"SELECT ticker FROM companies WHERE ticker IN ({placeholders})",
            tickers,
        )
        found = {r["ticker"] for r in cur.fetchall()}
        missing = [t for t in tickers if t not in found]

        results = []
        for ticker in tickers:
            if ticker in missing:
                results.append({"ticker": ticker, "error": "Company not found"})
                continue

            entry: dict = {"ticker": ticker}

            # Get company name
            cur.execute("SELECT name FROM companies WHERE ticker = ?", (ticker,))
            entry["name"] = cur.fetchone()["name"]

            # Fetch most recent financials
            cur.execute("""
                SELECT * FROM financials
                WHERE company_id = (SELECT id FROM companies WHERE ticker = ?)
                ORDER BY fiscal_year DESC LIMIT 1
            """, (ticker,))
            fin_row = cur.fetchone()
            fin_data = row_to_dict(fin_row) if fin_row else {}

            # Fetch most recent valuation
            cur.execute("""
                SELECT * FROM valuations
                WHERE company_id = (SELECT id FROM companies WHERE ticker = ?)
                ORDER BY as_of_date DESC LIMIT 1
            """, (ticker,))
            val_row = cur.fetchone()
            val_data = row_to_dict(val_row) if val_row else {}

            # Populate requested metrics
            for metric in metrics:
                table, col = METRIC_TABLE_MAP[metric]
                if table == "financials":
                    entry[metric] = fin_data.get(col)
                else:
                    entry[metric] = val_data.get(col)

            # Preserve source provenance for retrieved metrics
            if fin_data.get("source"):
                entry["financial_source"] = fin_data.get("source")
                entry["financial_source_url"] = fin_data.get("source_url")
            if val_data.get("source"):
                entry["valuation_source"] = val_data.get("source")
                entry["valuation_source_url"] = val_data.get("source_url")

            results.append(entry)

        if missing:
            return {
                "warning": f"Tickers not found: {', '.join(missing)}",
                "results": results,
            }

        return results

    finally:
        conn.close()
