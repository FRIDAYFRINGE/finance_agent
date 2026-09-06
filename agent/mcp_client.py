"""Model Context Protocol (MCP) Client Wrapper for the Financial Agent.

Connects to the local MCP Tool Server over stdio transport, discovers available
tools, translates tool schemas into OpenAI-compatible function definitions, and
executes live tool calls while extracting factual source provenance.
"""

import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class MCPClient:
    """Async MCP Client managing stdio session with mcp_server.server."""

    def __init__(self, server_command: Optional[str] = None, server_args: Optional[list[str]] = None):
        self.server_command = server_command or sys.executable
        self.server_args = server_args or ["-m", "mcp_server.server"]
        self._client_cm = None
        self._session_cm = None
        self.session: Optional[ClientSession] = None
        self._tools_cache: list[Any] = []

    async def start(self) -> None:
        """Starts the MCP server subprocess and performs protocol handshake."""
        if self.session is not None:
            return

        server_params = StdioServerParameters(
            command=self.server_command,
            args=self.server_args,
            env=os.environ.copy(),
        )

        self._client_cm = stdio_client(server_params)
        read_stream, write_stream = await self._client_cm.__aenter__()

        self._session_cm = ClientSession(read_stream, write_stream)
        self.session = await self._session_cm.__aenter__()

        await self.session.initialize()
        tools_resp = await self.session.list_tools()
        self._tools_cache = tools_resp.tools

    async def stop(self) -> None:
        """Closes the MCP session and terminates the subprocess."""
        if self._session_cm:
            try:
                await self._session_cm.__aexit__(None, None, None)
            except Exception:
                pass
            self._session_cm = None
            self.session = None

        if self._client_cm:
            try:
                await self._client_cm.__aexit__(None, None, None)
            except Exception:
                pass
            self._client_cm = None

    async def __aenter__(self) -> "MCPClient":
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.stop()

    async def list_tools(self) -> list[Any]:
        """Returns discovered MCP tools."""
        if not self._tools_cache:
            if not self.session:
                await self.start()
            tools_resp = await self.session.list_tools()
            self._tools_cache = tools_resp.tools
        return self._tools_cache

    async def get_tools_for_llm(self) -> list[dict[str, Any]]:
        """Converts MCP tool schemas into OpenAI-compatible tool specifications."""
        tools = await self.list_tools()
        llm_tools = []
        for tool in tools:
            # Map MCP tool definition to OpenAI tool function format
            params = getattr(tool, "input_schema", getattr(tool, "inputSchema", {}))
            llm_tools.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description or "",
                    "parameters": params,
                }
            })
        return llm_tools

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        """Executes an MCP tool call over stdio and deserializes the JSON result."""
        if not self.session:
            await self.start()

        result = await self.session.call_tool(tool_name, arguments)
        if not result.content:
            return {}

        raw_text = result.content[0].text
        try:
            return json.loads(raw_text)
        except json.JSONDecodeError:
            return {"raw_text": raw_text}

    @staticmethod
    def extract_provenance(tool_name: str, arguments: dict[str, Any], result_data: Any) -> tuple[list[dict[str, str]], set[str]]:
        """Extracts verified tickers and source provenance directly from MCP tool responses.
        
        Guarantees that data sources and referenced tickers come from actual database records
        rather than ungrounded LLM text generation.
        """
        sources: list[dict[str, str]] = []
        tickers: set[str] = set()

        if isinstance(result_data, dict):
            # Check for direct ticker argument
            if "ticker" in arguments and arguments["ticker"]:
                ticker = arguments["ticker"].upper()
                # Don't add ticker to referenced list if it was an out-of-scope not found error
                if not ("error" in result_data and "not found" in str(result_data["error"]).lower()):
                    tickers.add(ticker)

            # Tool: get_sector_overview
            if tool_name == "get_sector_overview" and "name" in result_data and "error" not in result_data:
                s_name = result_data.get("display_name") or result_data.get("name", "").title()
                as_of = result_data.get("data_as_of", "2024-12-31")
                metrics_summary = []
                for k in ["avg_pe_ttm", "avg_ev_ebitda", "avg_gross_margin_pct", "avg_operating_margin_pct", "avg_revenue_growth_pct"]:
                    if k in result_data and result_data[k] is not None:
                        metrics_summary.append(f"{k}: {result_data[k]}")
                if metrics_summary:
                    sources.append({
                        "company": f"Sector ({s_name})",
                        "metric_or_event": f"Sector Aggregates (as of {as_of}): {', '.join(metrics_summary)}",
                        "source": "Dynamic Sector Aggregates (SEC 10-K & Yahoo Finance)",
                        "source_url": "",
                    })

            # Tool: get_company_details
            if "company" in result_data and isinstance(result_data["company"], dict):
                ticker = result_data["company"].get("ticker", "")
                if ticker:
                    tickers.add(ticker)

                # Company Profile & Headcount
                comp = result_data.get("company", {})
                hc = comp.get("headcount")
                hc_pct = comp.get("headcount_change_pct")
                if hc is not None:
                    fin_list = result_data.get("financials", [])
                    fin_url = fin_list[0].get("source_url") if fin_list else ""
                    fin_src = fin_list[0].get("source") if fin_list else "SEC 10-K"
                    hc_desc = f"Company Profile & Headcount ({hc:,} employees"
                    if hc_pct is not None:
                        hc_desc += f", {hc_pct:+.1f}% YoY"
                    hc_desc += ")"
                    sources.append({
                        "company": ticker,
                        "metric_or_event": hc_desc,
                        "source": fin_src,
                        "source_url": fin_url,
                    })

                # Accounting Financials
                for fin in result_data.get("financials", []):
                    fy = fin.get("fiscal_year", "")
                    src = fin.get("source")
                    src_url = fin.get("source_url")
                    if src and src_url:
                        sources.append({
                            "company": ticker,
                            "metric_or_event": f"FY{fy} Accounting Financials (Revenue, Margins, Debt, FCF)",
                            "source": src,
                            "source_url": src_url,
                        })

                # Market Valuation
                val = result_data.get("valuation", {})
                if val and val.get("source") and val.get("source_url"):
                    sources.append({
                        "company": ticker,
                        "metric_or_event": f"Market Valuation Snapshot (P/E, EV/EBITDA, MktCap)",
                        "source": val["source"],
                        "source_url": val["source_url"],
                    })

                # News / Hiring Events (include summary for factual claims)
                for ev in result_data.get("recent_events", []):
                    if ev.get("source_url"):
                        summary = ev.get("summary")
                        ev_text = f"Event [{ev.get('event_type')}]: {ev.get('headline')}"
                        if summary:
                            ev_text += f" — {summary}"
                        sources.append({
                            "company": ticker,
                            "metric_or_event": ev_text,
                            "source": "Company News / Filing",
                            "source_url": ev["source_url"],
                        })

        elif isinstance(result_data, list):
            for item in result_data:
                if isinstance(item, dict):
                    t = item.get("ticker")
                    if t:
                        tickers.add(t.upper())

                    # Provenance from query_financials
                    if "metric_name" in item and "metric_value" in item and item.get("source"):
                        src = item["source"]
                        sources.append({
                            "company": t or item.get("name", "Unknown"),
                            "metric_or_event": f"Metric {item.get('metric_name', '')}: {item.get('metric_value', '')}",
                            "source": src,
                            "source_url": item.get("source_url") or "",
                        })

                    # Provenance from compare_companies
                    if "financial_source" in item and item.get("financial_source"):
                        sources.append({
                            "company": t or item.get("name", "Unknown"),
                            "metric_or_event": "Financial Metrics (from compare_companies)",
                            "source": item["financial_source"],
                            "source_url": item.get("financial_source_url") or "",
                        })
                    if "valuation_source" in item and item.get("valuation_source"):
                        val_src = item["valuation_source"]
                        sources.append({
                            "company": t or item.get("name", "Unknown"),
                            "metric_or_event": "Valuation Metrics (from compare_companies)",
                            "source": val_src,
                            "source_url": item.get("valuation_source_url") or "",
                        })

                    # Provenance from search_news_events (include summary for factual claims)
                    if "headline" in item and item.get("source_url"):
                        summary = item.get("summary")
                        ev_text = f"Event [{item.get('event_type')}]: {item.get('headline')}"
                        if summary:
                            ev_text += f" — {summary}"
                        sources.append({
                            "company": t or "Sector News",
                            "metric_or_event": ev_text,
                            "source": "Public Corporate News",
                            "source_url": item["source_url"],
                        })

        return sources, tickers
