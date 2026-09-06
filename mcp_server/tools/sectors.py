"""Sector-related MCP tools: list_sectors, get_sector_overview.

These tools query the `sectors` table and compute dynamic aggregates by
joining through `companies` → `financials` / `valuations`.
"""

from mcp_server.db import get_connection, rows_to_list, row_to_dict
from mcp_server.config import VALID_SECTORS


def list_sectors() -> list[dict]:
    """Returns the list of available sectors with summary info.

    Returns:
        List of dicts, each containing:
        - name, display_name, overview, tailwinds, headwinds, company_count
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT
                s.name,
                s.display_name,
                s.overview,
                s.tailwinds,
                s.headwinds,
                s.data_as_of,
                COUNT(c.id) AS company_count
            FROM sectors s
            LEFT JOIN companies c ON c.sector_id = s.id
            GROUP BY s.id
            ORDER BY s.name
        """)
        return rows_to_list(cur.fetchall())
    finally:
        conn.close()


def get_sector_overview(sector: str) -> dict:
    """Returns detailed overview for a sector with dynamically computed aggregates.

    Args:
        sector: One of 'tech', 'retail', 'logistics'.

    Returns:
        Dict containing sector info plus computed averages:
        - name, display_name, overview, tailwinds, headwinds, data_as_of
        - company_count
        - avg_pe_ttm, avg_ev_ebitda, avg_gross_margin_pct,
          avg_operating_margin_pct, avg_revenue_growth_pct
    """
    sector = sector.strip().lower()
    if sector not in VALID_SECTORS:
        return {
            "error": f"Invalid sector '{sector}'. Must be one of: {', '.join(sorted(VALID_SECTORS))}"
        }

    conn = get_connection()
    try:
        cur = conn.cursor()

        # Fetch base sector info + company count
        cur.execute("""
            SELECT
                s.name,
                s.display_name,
                s.overview,
                s.tailwinds,
                s.headwinds,
                s.data_as_of,
                COUNT(c.id) AS company_count
            FROM sectors s
            LEFT JOIN companies c ON c.sector_id = s.id
            WHERE s.name = ?
            GROUP BY s.id
        """, (sector,))
        row = cur.fetchone()
        if not row:
            return {"error": f"Sector '{sector}' not found in database."}

        result = row_to_dict(row)

        # Compute average P/E and EV/EBITDA from valuations
        cur.execute("""
            SELECT
                ROUND(AVG(v.pe_ttm), 2)    AS avg_pe_ttm,
                ROUND(AVG(v.ev_ebitda), 2) AS avg_ev_ebitda
            FROM valuations v
            JOIN companies c ON v.company_id = c.id
            JOIN sectors s   ON c.sector_id  = s.id
            WHERE s.name = ?
        """, (sector,))
        val_row = cur.fetchone()
        if val_row:
            result["avg_pe_ttm"] = val_row["avg_pe_ttm"]
            result["avg_ev_ebitda"] = val_row["avg_ev_ebitda"]

        # Compute average margin and growth from MOST RECENT financials per company
        cur.execute("""
            SELECT
                ROUND(AVG(f.gross_margin_pct), 2)     AS avg_gross_margin_pct,
                ROUND(AVG(f.operating_margin_pct), 2) AS avg_operating_margin_pct,
                ROUND(AVG(f.revenue_growth_pct), 2)   AS avg_revenue_growth_pct
            FROM financials f
            JOIN companies c ON f.company_id = c.id
            JOIN sectors s   ON c.sector_id  = s.id
            WHERE s.name = ?
              AND f.fiscal_year = (
                  SELECT MAX(f2.fiscal_year)
                  FROM financials f2
                  WHERE f2.company_id = f.company_id
              )
        """, (sector,))
        fin_row = cur.fetchone()
        if fin_row:
            result["avg_gross_margin_pct"] = fin_row["avg_gross_margin_pct"]
            result["avg_operating_margin_pct"] = fin_row["avg_operating_margin_pct"]
            result["avg_revenue_growth_pct"] = fin_row["avg_revenue_growth_pct"]

        return result

    finally:
        conn.close()
