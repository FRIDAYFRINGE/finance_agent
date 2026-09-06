
import asyncio
import sys
from pathlib import Path

# Ensure project root in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from mcp_server.tools.financials import query_financials
from mcp_server.tools.companies import compare_companies, get_company_details
from mcp_server.tools.sectors import get_sector_overview
from mcp_server.tools.news import search_news_events
from agent.mcp_client import MCPClient
from agent.personas.base import BASE_INSTRUCTIONS
from agent.personas import build_system_prompt
from agent.core import FinancialAgent
from agent.response import DataSourceRecord
from scripts.run_live_validation import LoggingFinancialAgent


passed_tests = 0
failed_tests = 0


def track(name: str, condition: bool, detail: str = ""):
    global passed_tests, failed_tests
    if condition:
        passed_tests += 1
        print(f"  [PASS] {name}" + (f" -- {detail}" if detail else ""))
    else:
        failed_tests += 1
        print(f"  [FAIL] {name}" + (f" -- {detail}" if detail else ""))


class MockLLMMessage:
    def __init__(self, content="", tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or []

    def model_dump(self):
        return {"role": "assistant", "content": self.content}


class MockToolCall:
    def __init__(self, call_id, name, args):
        self.id = call_id
        self.function = type("Fn", (), {"name": name, "arguments": str(args).replace("'", '"')})()


class MockChoice:
    def __init__(self, message):
        self.message = message


class MockCompletion:
    def __init__(self, message, prompt_tokens=100, completion_tokens=50):
        self.choices = [MockChoice(message)]
        self.usage = type("Usage", (), {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        })()


class ScriptedMockLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.call_count = 0
        self.chat = self
        self.completions = self

    async def create(self, *args, **kwargs):
        if self.call_count < len(self.responses):
            resp = self.responses[self.call_count]
            self.call_count += 1
            return MockCompletion(resp)
        return MockCompletion(MockLLMMessage("End of mock responses."))


async def run_regression_tests():
    print("=" * 80)
    print("  PHASE 3 AUDIT REGRESSION TEST SUITE (Issues 1 - 5)")
    print("=" * 80)

    # ------------------------------------------------------------------
    # 1. ISSUE 1: Provenance URLs
    # ------------------------------------------------------------------
    print("\n[ISSUE 1] Testing query_financials source_url preservation...")
    
    # 1.1 Valuations (Yahoo Finance)
    q_val = query_financials("logistics", "ev_ebitda", limit=5)
    track("query_financials (valuation) returns list", isinstance(q_val, list) and len(q_val) > 0)
    track("query_financials (valuation) row contains 'source_url'", "source_url" in q_val[0])
    track("query_financials (valuation) source is 'Yahoo Finance'", q_val[0].get("source") == "Yahoo Finance")
    track(
        "query_financials (valuation) source_url is Yahoo Finance URL",
        "finance.yahoo.com" in q_val[0].get("source_url", ""),
        q_val[0].get("source_url")
    )
    track(
        "query_financials (valuation) source_url is NOT SEC EDGAR",
        "sec.gov" not in q_val[0].get("source_url", "")
    )

    # 1.2 Financials (SEC 10-K)
    q_fin = query_financials("logistics", "debt_to_ebitda", limit=5)
    track("query_financials (financial) row contains 'source_url'", "source_url" in q_fin[0])
    track("query_financials (financial) source is SEC 10-K", "SEC 10-K" in q_fin[0].get("source", ""))
    track(
        "query_financials (financial) source_url has SEC EDGAR accession URL",
        ("sec.gov/ix?doc=/Archives/edgar/data/" in q_fin[0].get("source_url", "")) or ("sec.gov/Archives/edgar/data/" in q_fin[0].get("source_url", "")),
        q_fin[0].get("source_url")
    )

    # 1.3 Client extraction of query_financials
    srcs_val, _ = MCPClient.extract_provenance("query_financials", {}, q_val)
    track("extract_provenance preserves Yahoo Finance URL", "finance.yahoo.com" in srcs_val[0]["source_url"])
    track("extract_provenance does NOT substitute SEC URL for Yahoo", "sec.gov" not in srcs_val[0]["source_url"])

    srcs_fin, _ = MCPClient.extract_provenance("query_financials", {}, q_fin)
    track("extract_provenance preserves exact SEC accession URL", "Archives/edgar/data" in srcs_fin[0]["source_url"])

    # ------------------------------------------------------------------
    # 2. ISSUE 2: Provenance Coverage Gap
    # ------------------------------------------------------------------
    print("\n[ISSUE 2] Testing comprehensive provenance aggregation...")

    # 2.1 compare_companies
    cmp_res = compare_companies(["UPS", "FDX", "XPO"])
    track("compare_companies contains financial_source", "financial_source" in cmp_res[0])
    track("compare_companies contains valuation_source_url", "valuation_source_url" in cmp_res[0])
    cmp_srcs, cmp_tickers = MCPClient.extract_provenance("compare_companies", {}, cmp_res)
    track("extract_provenance extracts records from compare_companies", len(cmp_srcs) > 0, f"found {len(cmp_srcs)}")
    track("compare_companies tickers extracted", "UPS" in cmp_tickers and "FDX" in cmp_tickers)
    has_yahoo = any("finance.yahoo.com" in s["source_url"] for s in cmp_srcs)
    has_sec = any("sec.gov" in s["source_url"] for s in cmp_srcs)
    track("compare_companies has both Yahoo and SEC URLs", has_yahoo and has_sec)

    # 2.2 get_sector_overview (dynamically computed multi-source aggregate)
    sec_res = get_sector_overview("logistics")
    sec_srcs, _ = MCPClient.extract_provenance("get_sector_overview", {}, sec_res)
    track("get_sector_overview provenance extracted", len(sec_srcs) == 1)
    track("sector overview contains dynamic aggregate label", "Sector Aggregates" in sec_srcs[0]["metric_or_event"])
    track(
        "sector aggregate does NOT fabricate generic SEC URL",
        "sec.gov" not in sec_srcs[0].get("source_url", "") and sec_srcs[0].get("source_url") == "",
        f"source_url='{sec_srcs[0].get('source_url')}'"
    )

    # 2.3 get_company_details (headcount + news summary)
    gxo_det = get_company_details("GXO")
    gxo_srcs, _ = MCPClient.extract_provenance("get_company_details", {"ticker": "GXO"}, gxo_det)
    has_hc = any("Headcount" in s["metric_or_event"] and ("130,000" in s["metric_or_event"] or "152,000" in s["metric_or_event"]) for s in gxo_srcs)
    track("company profile headcount is present in provenance", has_hc)

    has_retention_summary = any("95%" in s["metric_or_event"] or "retention" in s["metric_or_event"] for s in gxo_srcs)
    track("news event summary context (e.g. 95% retention) is captured in provenance", has_retention_summary)

    # 2.4 search_news_events summary
    news_res = search_news_events(ticker="NVDA", event_type="hiring")
    news_srcs, _ = MCPClient.extract_provenance("search_news_events", {}, news_res)
    has_news_summary = any("architects" in s["metric_or_event"] or "packaging" in s["metric_or_event"] for s in news_srcs)
    track("search_news_events summary context captured in provenance", has_news_summary)

    # ------------------------------------------------------------------
    # 3. ISSUE 3: Confidence Logic
    # ------------------------------------------------------------------
    print("\n[ISSUE 3] Testing evidence-based confidence determination...")

    # 3.1 Unknown company query with natural refusal prose (TSLA)
    mock_oos = ScriptedMockLLM([
        MockLLMMessage(content="", tool_calls=[MockToolCall("call_oos", "get_company_details", {"ticker": "TSLA"})]),
        MockLLMMessage(content="I don't have coverage on TSLA in my database. Tesla does not appear in my available records for Technology, Retail, or Logistics. I cannot provide an ungrounded view."),
    ])

    async with FinancialAgent("mf_analyst", "tech", llm_client=mock_oos) as agent:
        resp_oos = await agent.query("What do you think about TSLA?")
        track("TSLA query returns medium confidence (honest refusal)", resp_oos.confidence == "medium")
        track("TSLA query confidence is NOT high", resp_oos.confidence != "high")
        track("TSLA query data_sources count is 0", len(resp_oos.data_sources) == 0)

    # 3.2 Query with zero data sources and no OOS refusal
    mock_zero = ScriptedMockLLM([
        MockLLMMessage(content="Here is some general text without tools or sources."),
    ])
    async with FinancialAgent("mf_analyst", "tech", llm_client=mock_zero) as agent:
        resp_zero = await agent.query("General question")
        track("Zero data sources without OOS refusal returns 'low' confidence", resp_zero.confidence == "low")

    # 3.3 Query with partial data (e.g. 1 source)
    mock_partial = ScriptedMockLLM([
        MockLLMMessage(content="", tool_calls=[MockToolCall("call_sec", "get_sector_overview", {"sector": "tech"})]),
        MockLLMMessage(content="Based only on sector aggregates, tech shows strong growth."),
    ])
    async with FinancialAgent("mf_analyst", "tech", llm_client=mock_partial) as agent:
        resp_partial = await agent.query("Sector overview")
        track("Partial data (1 source) returns 'medium' confidence", resp_partial.confidence == "medium")

    # 3.4 Query with strong data (>= 3 sources)
    mock_rich = ScriptedMockLLM([
        MockLLMMessage(content="", tool_calls=[MockToolCall("call_comp", "compare_companies", {"tickers": ["UPS", "FDX"]})]),
        MockLLMMessage(content="Comparing UPS and FDX with comprehensive data."),
    ])
    async with FinancialAgent("pe_analyst", "logistics", llm_client=mock_rich) as agent:
        resp_rich = await agent.query("Compare UPS and FDX")
        track("Rich data (>=3 sources) returns 'high' confidence", resp_rich.confidence == "high")

    # ------------------------------------------------------------------
    # 4. ISSUE 4: Historical-Time Wording Prompt Directive
    # ------------------------------------------------------------------
    print("\n[ISSUE 4] Testing temporal grounding prompt directives...")
    prompt = build_system_prompt("pe_analyst", "logistics")
    track("Prompt contains 'Strict Temporal Grounding'", "Strict Temporal Grounding" in prompt)
    track("Prompt forbids 'today', 'currently', or 'right now'", "Never describe database records as \"current\", \"today\", or \"right now\"" in prompt)
    track("Prompt mandates 'Based on the 2024 snapshot'", "Based on the 2024 snapshot" in prompt)
    track("Prompt anchors valuation snapshot as of December 31, 2024", "December 31, 2024" in prompt)

    # ------------------------------------------------------------------
    # 5. ISSUE 5: Harness Duplication & Observability
    # ------------------------------------------------------------------
    print("\n[ISSUE 5] Testing LoggingFinancialAgent reuse of core agent...")
    mock_harness_llm = ScriptedMockLLM([
        MockLLMMessage(content="", tool_calls=[MockToolCall("call_h", "get_sector_overview", {"sector": "tech"})]),
        MockLLMMessage(content="Tech sector overview analysis complete."),
    ])

    harness_agent = LoggingFinancialAgent("equity_analyst", "tech", llm_client=mock_harness_llm)
    async with harness_agent:
        h_resp = await harness_agent.query("Analyze tech sector")
        track("LoggingFinancialAgent successfully executes query()", len(h_resp.answer) > 0)
        track("LoggingFinancialAgent tracks api_call_count natively", harness_agent.api_call_count == 2)
        track("LoggingFinancialAgent tracks token_usage natively", harness_agent.token_usage["total_tokens"] > 0)
        track("LoggingFinancialAgent live_tool_sequence has tool entry", len(harness_agent.live_tool_sequence) == 1)
        track("live_tool_sequence records tool name and iteration", harness_agent.live_tool_sequence[0]["tool"] == "get_sector_overview")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print("\n" + "=" * 80)
    print(f"  REGRESSION SUITE RESULTS: {passed_tests} passed, {failed_tests} failed, {passed_tests + failed_tests} total")
    print("=" * 80)

    if failed_tests > 0:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(run_regression_tests())
