"""News/events search MCP tool: search_news_events.

Supports flexible filtering by sector, ticker, event type, and sentiment.
"""

from mcp_server.db import get_connection, rows_to_list
from mcp_server.config import VALID_SECTORS, VALID_EVENT_TYPES, VALID_SENTIMENTS


def search_news_events(
    sector: str | None = None,
    ticker: str | None = None,
    event_type: str | None = None,
    sentiment: str | None = None,
    limit: int = 10,
) -> list[dict] | dict:
    """Search news and events by company, sector, type, or sentiment.

    At least one of ``sector`` or ``ticker`` must be provided.

    Args:
        sector: Filter by sector name (optional).
        ticker: Filter by company ticker (optional).
        event_type: Filter by event type, e.g. 'earnings', 'hiring' (optional).
        sentiment: Filter by 'positive', 'negative', or 'neutral' (optional).
        limit: Maximum results. Default: 10.

    Returns:
        List of dicts with: company_name, ticker, event_date, event_type,
        headline, summary, sentiment, source_url.
        Or error dict if validation fails.
    """
    # --- At least one filter required ---
    if not sector and not ticker:
        return {"error": "At least one of 'sector' or 'ticker' must be provided."}

    # --- Validate optional params ---
    if sector:
        sector = sector.strip().lower()
        if sector not in VALID_SECTORS:
            return {
                "error": f"Invalid sector '{sector}'. Must be one of: {', '.join(sorted(VALID_SECTORS))}"
            }

    if ticker:
        ticker = ticker.strip().upper()

    if event_type:
        event_type = event_type.strip()
        if event_type not in VALID_EVENT_TYPES:
            return {
                "error": f"Invalid event_type '{event_type}'. "
                         f"Must be one of: {', '.join(sorted(VALID_EVENT_TYPES))}"
            }

    if sentiment:
        sentiment = sentiment.strip().lower()
        if sentiment not in VALID_SENTIMENTS:
            return {
                "error": f"Invalid sentiment '{sentiment}'. "
                         f"Must be one of: {', '.join(sorted(VALID_SENTIMENTS))}"
            }

    # --- Build query dynamically (with parameterised values only) ---
    query = """
        SELECT
            c.name  AS company_name,
            c.ticker,
            n.event_date,
            n.event_type,
            n.headline,
            n.summary,
            n.sentiment,
            n.source_url
        FROM news_events n
        JOIN companies c ON n.company_id = c.id
        JOIN sectors s   ON c.sector_id  = s.id
        WHERE 1 = 1
    """
    params: list = []

    if sector:
        query += "  AND s.name = ?\n"
        params.append(sector)

    if ticker:
        query += "  AND c.ticker = ?\n"
        params.append(ticker)

    if event_type:
        query += "  AND n.event_type = ?\n"
        params.append(event_type)

    if sentiment:
        query += "  AND n.sentiment = ?\n"
        params.append(sentiment)

    query += "  ORDER BY n.event_date DESC\n"
    query += "  LIMIT ?\n"
    params.append(limit)

    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(query, params)
        results = rows_to_list(cur.fetchall())

        # If ticker was provided but yielded no results, check if ticker exists
        if not results and ticker:
            cur.execute("SELECT COUNT(*) AS cnt FROM companies WHERE ticker = ?", (ticker,))
            if cur.fetchone()["cnt"] == 0:
                return {"error": f"Company not found for ticker '{ticker}'."}

        return results

    finally:
        conn.close()
