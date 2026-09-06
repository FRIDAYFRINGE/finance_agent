"""Standalone test script for MCP tool functions.

Tests each of the 7 tools by calling the underlying Python functions
directly (no MCP protocol needed).  This validates data access, SQL
queries, error handling, and response shapes before running via MCP.

Usage:
    python scripts/test_mcp_tools.py
"""

import json
import sys
import os

# Ensure project root is on the path so `mcp_server` package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from mcp_server.tools.sectors import list_sectors, get_sector_overview
from mcp_server.tools.companies import list_companies, get_company_details, compare_companies
from mcp_server.tools.financials import query_financials
from mcp_server.tools.news import search_news_events


def sep(title: str):
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}")


def check(label: str, condition: bool, detail: str = ""):
    status = "PASS" if condition else "FAIL"
    msg = f"  [{status}] {label}"
    if detail:
        msg += f"  --  {detail}"
    print(msg)
    return condition


def main():
    passed = 0
    failed = 0

    def track(ok: bool):
        nonlocal passed, failed
        if ok:
            passed += 1
        else:
            failed += 1

    # ===================================================================
    # Test 1: list_sectors
    # ===================================================================
    sep("Test 1: list_sectors()")
    result = list_sectors()
    print(f"  Returned {len(result)} sectors")
    track(check("Returns 3 sectors", len(result) == 3))
    names = {s["name"] for s in result}
    track(check("Contains tech, retail, logistics", names == {"tech", "retail", "logistics"}))
    for s in result:
        track(check(
            f"  {s['name']}: company_count = {s['company_count']}",
            s["company_count"] == 7,
            f"expected 7"
        ))
        track(check(f"  {s['name']}: has overview", bool(s.get("overview"))))

    # ===================================================================
    # Test 2: get_sector_overview
    # ===================================================================
    sep("Test 2: get_sector_overview('logistics')")
    result = get_sector_overview("logistics")
    print(f"  Result keys: {list(result.keys())}")
    track(check("No error", "error" not in result))
    track(check("Has avg_pe_ttm", result.get("avg_pe_ttm") is not None, str(result.get("avg_pe_ttm"))))
    track(check("Has avg_ev_ebitda", result.get("avg_ev_ebitda") is not None, str(result.get("avg_ev_ebitda"))))
    track(check("Has avg_gross_margin_pct", result.get("avg_gross_margin_pct") is not None, str(result.get("avg_gross_margin_pct"))))
    track(check("Has avg_revenue_growth_pct", result.get("avg_revenue_growth_pct") is not None, str(result.get("avg_revenue_growth_pct"))))
    track(check("company_count = 7", result.get("company_count") == 7))

    # Invalid sector
    sep("Test 2b: get_sector_overview('crypto') — invalid sector")
    result = get_sector_overview("crypto")
    track(check("Returns error", "error" in result, result.get("error", "")))

    # ===================================================================
    # Test 3: list_companies
    # ===================================================================
    sep("Test 3: list_companies('tech')")
    result = list_companies("tech")
    print(f"  Returned {len(result)} companies")
    track(check("Returns 7 companies", len(result) == 7))
    if result and "error" not in result[0]:
        tickers = [c["ticker"] for c in result]
        track(check("NVDA in results", "NVDA" in tickers))
        track(check("Has market_cap", result[0].get("market_cap") is not None))
        track(check("Has revenue", result[0].get("revenue") is not None))

    # Test sorting by name
    sep("Test 3b: list_companies('retail', sort_by='name', limit=3)")
    result = list_companies("retail", sort_by="name", limit=3)
    track(check("Returns 3 companies (limit)", len(result) == 3))
    if len(result) >= 2:
        track(check("Sorted by name", result[0]["name"] <= result[1]["name"]))

    # ===================================================================
    # Test 4: get_company_details
    # ===================================================================
    sep("Test 4: get_company_details('NVDA')")
    result = get_company_details("NVDA")
    track(check("No error", "error" not in result))
    track(check("Has company key", "company" in result))
    track(check("Has financials key", "financials" in result))
    track(check("Has valuation key", "valuation" in result))
    track(check("Has recent_events key", "recent_events" in result))

    if "company" in result:
        c = result["company"]
        track(check("Ticker is NVDA", c.get("ticker") == "NVDA"))
        track(check("Has headcount", c.get("headcount") is not None, str(c.get("headcount"))))
        track(check("Has headcount_change_pct", c.get("headcount_change_pct") is not None))

    if "financials" in result:
        track(check("Has >= 2 financial years", len(result["financials"]) >= 2))
        if result["financials"]:
            f = result["financials"][0]
            track(check("Financials have source", bool(f.get("source"))))
            track(check("Financials have source_url", bool(f.get("source_url"))))

    if "valuation" in result and result["valuation"]:
        v = result["valuation"]
        track(check("Valuation has market_cap", v.get("market_cap") is not None))
        track(check("Valuation has source", bool(v.get("source"))))

    if "recent_events" in result:
        track(check("Has >= 2 events", len(result["recent_events"]) >= 2))

    # Unknown ticker
    sep("Test 4b: get_company_details('TSLA') — not in DB")
    result = get_company_details("TSLA")
    track(check("Returns error", "error" in result, result.get("error", "")))
    track(check("Error mentions ticker", result.get("ticker") == "TSLA"))

    # ===================================================================
    # Test 5: compare_companies
    # ===================================================================
    sep("Test 5: compare_companies(['UPS', 'FDX', 'XPO'])")
    result = compare_companies(["UPS", "FDX", "XPO"])
    if isinstance(result, list):
        track(check("Returns 3 companies", len(result) == 3))
        if result:
            track(check("Has revenue metric", "revenue" in result[0]))
            track(check("Has pe_ttm metric", "pe_ttm" in result[0]))
            track(check("Has market_cap metric", "market_cap" in result[0]))
    else:
        track(check("Returns list (not error)", False, str(result)))

    # Compare with unknown ticker
    sep("Test 5b: compare_companies(['NVDA', 'TSLA']) — one unknown")
    result = compare_companies(["NVDA", "TSLA"])
    track(check("Returns warning about missing", isinstance(result, dict) and "warning" in result,
                str(result.get("warning", "")) if isinstance(result, dict) else ""))

    # Too few tickers
    sep("Test 5c: compare_companies(['NVDA']) — too few")
    result = compare_companies(["NVDA"])
    track(check("Returns error for < 2 tickers", isinstance(result, dict) and "error" in result))

    # ===================================================================
    # Test 6: search_news_events
    # ===================================================================
    sep("Test 6: search_news_events(ticker='NVDA', event_type='hiring')")
    result = search_news_events(ticker="NVDA", event_type="hiring")
    if isinstance(result, list):
        track(check("Returns hiring events", len(result) > 0, f"found {len(result)}"))
        if result:
            track(check("Event has headline", bool(result[0].get("headline"))))
            track(check("Event type is hiring", result[0].get("event_type") == "hiring"))
    else:
        track(check("Returns list", False, str(result)))

    # Search by sector
    sep("Test 6b: search_news_events(sector='retail')")
    result = search_news_events(sector="retail")
    if isinstance(result, list):
        track(check("Returns retail events", len(result) > 0, f"found {len(result)}"))
    else:
        track(check("Returns list", False, str(result)))

    # No params
    sep("Test 6c: search_news_events() — no params")
    result = search_news_events()
    track(check("Returns error (no params)", isinstance(result, dict) and "error" in result))

    # ===================================================================
    # Test 7: query_financials
    # ===================================================================
    sep("Test 7a: query_financials('logistics', 'debt_to_ebitda', order='desc')")
    result = query_financials("logistics", "debt_to_ebitda", order="desc")
    if isinstance(result, list):
        track(check("Returns results", len(result) > 0, f"found {len(result)}"))
        if len(result) >= 2:
            # Check descending order
            vals = [r["metric_value"] for r in result if r["metric_value"] is not None]
            is_desc = all(vals[i] >= vals[i+1] for i in range(len(vals)-1))
            track(check("Sorted descending", is_desc, str(vals)))
    else:
        track(check("Returns list", False, str(result)))

    sep("Test 7b: query_financials('tech', 'gross_margin_pct', order='desc')")
    result = query_financials("tech", "gross_margin_pct", order="desc")
    if isinstance(result, list):
        track(check("Returns tech companies", len(result) > 0))
        if result:
            track(check("Metric name correct", result[0].get("metric_name") == "gross_margin_pct"))
    else:
        track(check("Returns list", False, str(result)))

    sep("Test 7c: query_financials('retail', 'pe_ttm', max_value=20)")
    result = query_financials("retail", "pe_ttm", max_value=20)
    if isinstance(result, list):
        print(f"  Found {len(result)} retail companies with pe_ttm <= 20")
        for r in result:
            print(f"    {r['ticker']}: pe_ttm = {r['metric_value']}")
        if result:
            all_under = all(r["metric_value"] <= 20 for r in result if r["metric_value"] is not None)
            track(check("All pe_ttm <= 20", all_under))
        else:
            track(check("Query returned results (may be empty)", True, "no companies match filter"))
    else:
        track(check("Returns list", False, str(result)))

    # Invalid metric (SQL injection test)
    sep("Test 7d: query_financials('tech', 'DROP TABLE companies') — SQL injection")
    result = query_financials("tech", "DROP TABLE companies")
    track(check("Blocked by whitelist", isinstance(result, dict) and "error" in result, str(result.get("error", ""))))

    # ===================================================================
    # Summary
    # ===================================================================
    print(f"\n{'=' * 70}")
    print(f"  RESULTS: {passed} passed, {failed} failed, {passed + failed} total")
    print(f"{'=' * 70}\n")

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
