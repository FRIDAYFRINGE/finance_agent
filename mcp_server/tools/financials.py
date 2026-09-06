"""Financial ranking/filtering MCP tool: query_financials.

Allows ranking or filtering companies within a sector by any financial
or valuation metric.  Uses a strict whitelist to prevent SQL injection.
"""

from mcp_server.db import get_connection, rows_to_list
from mcp_server.config import (
    VALID_SECTORS,
    METRIC_TABLE_MAP,
    ALL_METRIC_NAMES,
)


def query_financials(
    sector: str,
    metric: str,
    order: str = "desc",
    min_value: float | None = None,
    max_value: float | None = None,
    limit: int = 10,
) -> list[dict] | dict:
    """Rank or filter companies by a financial or valuation metric within a sector.

    Args:
        sector: One of 'tech', 'retail', 'logistics'.
        metric: The metric to rank by (must be in the whitelist).
        order: 'asc' or 'desc'. Default: 'desc'.
        min_value: Optional minimum threshold for the metric.
        max_value: Optional maximum threshold for the metric.
        limit: Maximum results to return. Default: 10.

    Returns:
        List of dicts with: ticker, name, metric_name, metric_value, source, source_url.
        Or error dict if validation fails.
    """
    # --- Validation ---
    sector = sector.strip().lower()
    if sector not in VALID_SECTORS:
        return {"error": f"Invalid sector '{sector}'. Must be one of: {', '.join(sorted(VALID_SECTORS))}"}

    metric = metric.strip().lower()
    if metric not in METRIC_TABLE_MAP:
        return {
            "error": f"Unknown metric '{metric}'. "
                     f"Allowed: {', '.join(ALL_METRIC_NAMES)}"
        }

    order = order.strip().lower()
    if order not in ("asc", "desc"):
        order = "desc"

    table, column = METRIC_TABLE_MAP[metric]

    conn = get_connection()
    try:
        cur = conn.cursor()

        if table == "financials":
            # Use most recent fiscal year per company
            query = f"""
                SELECT
                    c.ticker,
                    c.name,
                    ? AS metric_name,
                    f.{column} AS metric_value,
                    f.source,
                    f.source_url
                FROM financials f
                JOIN companies c ON f.company_id = c.id
                JOIN sectors s   ON c.sector_id  = s.id
                WHERE s.name = ?
                  AND f.fiscal_year = (
                      SELECT MAX(f2.fiscal_year)
                      FROM financials f2
                      WHERE f2.company_id = f.company_id
                  )
                  AND f.{column} IS NOT NULL
            """
            params: list = [metric, sector]

        else:  # valuations
            query = f"""
                SELECT
                    c.ticker,
                    c.name,
                    ? AS metric_name,
                    v.{column} AS metric_value,
                    v.source,
                    v.source_url
                FROM valuations v
                JOIN companies c ON v.company_id = c.id
                JOIN sectors s   ON c.sector_id  = s.id
                WHERE s.name = ?
                  AND v.{column} IS NOT NULL
            """
            params = [metric, sector]

        # Apply optional min/max filters
        if min_value is not None:
            if table == "financials":
                query += f"  AND f.{column} >= ?\n"
            else:
                query += f"  AND v.{column} >= ?\n"
            params.append(min_value)

        if max_value is not None:
            if table == "financials":
                query += f"  AND f.{column} <= ?\n"
            else:
                query += f"  AND v.{column} <= ?\n"
            params.append(max_value)

        # ORDER BY and LIMIT — these use the whitelisted column, not user input
        order_dir = "ASC" if order == "asc" else "DESC"
        query += f"  ORDER BY metric_value {order_dir}\n"
        query += "  LIMIT ?\n"
        params.append(limit)

        cur.execute(query, params)
        return rows_to_list(cur.fetchall())

    finally:
        conn.close()
