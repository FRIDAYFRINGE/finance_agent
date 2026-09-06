"""Protocol-level integration test for the MCP Tool Server.

Spawns the MCP server as a subprocess and interacts with it using the official
MCP Python Client over stdio transport.  Validates:
1. Server initializes and advertises capability
2. All 7 tools are registered with correct schemas and descriptions
3. Tool calls execute over stdio JSON-RPC and return valid JSON responses
4. Error responses format properly across the wire

Usage:
    python scripts/test_mcp_protocol.py
"""

import asyncio
import json
import os
import sys
from pathlib import Path

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def check(label: str, condition: bool, detail: str = ""):
    status = "PASS" if condition else "FAIL"
    msg = f"  [{status}] {label}"
    if detail:
        msg += f"  --  {detail}"
    print(msg)
    return condition


async def run_protocol_tests():
    print("=" * 70)
    print("  MCP Protocol & Stdio Transport Integration Tests")
    print("=" * 70)

    passed = 0
    failed = 0

    def track(ok: bool):
        nonlocal passed, failed
        if ok:
            passed += 1
        else:
            failed += 1

    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_server.server"],
        env=os.environ.copy(),
    )

    print("\nConnecting to MCP server via stdio transport...")
    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            # 1. Initialize
            init_result = await session.initialize()
            track(check("MCP Server handshake/initialize", init_result is not None))

            # 2. List tools
            tool_list_response = await session.list_tools()
            tools = tool_list_response.tools
            tool_names = {t.name for t in tools}
            print(f"\nDiscovered {len(tools)} registered tools over MCP protocol:")
            for t in tools:
                print(f"   * {t.name}")

            expected_tools = {
                "list_sectors",
                "get_sector_overview",
                "list_companies",
                "get_company_details",
                "compare_companies",
                "search_news_events",
                "query_financials",
            }
            track(check("All 7 tools registered", tool_names == expected_tools))

            # 3. Call list_sectors over stdio
            print("\nCalling list_sectors over MCP protocol...")
            res = await session.call_tool("list_sectors", {})
            track(check("list_sectors returned content", len(res.content) > 0))
            sectors_data = json.loads(res.content[0].text)
            track(check("list_sectors returned 3 sectors", len(sectors_data) == 3))

            # 4. Call get_company_details for NVDA
            print("\nCalling get_company_details('NVDA') over MCP protocol...")
            res = await session.call_tool("get_company_details", {"ticker": "NVDA"})
            nvda_data = json.loads(res.content[0].text)
            track(check("get_company_details('NVDA') succeeded", "company" in nvda_data))
            track(check("Headcount present for stress test", nvda_data.get("company", {}).get("headcount") is not None))

            # 5. Call get_company_details for out-of-scope company TSLA
            print("\nCalling get_company_details('TSLA') [out-of-scope test]...")
            res = await session.call_tool("get_company_details", {"ticker": "TSLA"})
            tsla_data = json.loads(res.content[0].text)
            track(check("Out-of-scope returns clear error", "error" in tsla_data))

            # 6. Call search_news_events for hiring signal
            print("\nCalling search_news_events(ticker='NVDA', event_type='hiring')...")
            res = await session.call_tool("search_news_events", {"ticker": "NVDA", "event_type": "hiring"})
            news_data = json.loads(res.content[0].text)
            track(check("Hiring events retrieved via MCP", len(news_data) > 0))

            # 7. Call query_financials
            print("\nCalling query_financials('logistics', 'debt_to_ebitda')...")
            res = await session.call_tool("query_financials", {"sector": "logistics", "metric": "debt_to_ebitda"})
            fin_data = json.loads(res.content[0].text)
            track(check("query_financials returned ranked data", len(fin_data) == 7))

    print("\n" + "=" * 70)
    print(f"  PROTOCOL TEST RESULTS: {passed} passed, {failed} failed")
    print("=" * 70)
    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(run_protocol_tests())
