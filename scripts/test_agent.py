"""Comprehensive Test Suite for Phase 3: Persona-Configurable Financial Agent.

Tiered Testing Architecture:
  Tier 1: Unit Tests (Matrix, prompts, boundaries, data models) -- 0 credits, offline
  Tier 2: MCP Integration Tests (stdio handshake, schema conversion, tool calls) -- 0 LLM credits
  Tier 3: Mock Agent Tests (Full tool-calling loop, provenance, AgentResponse) -- 0 credits, offline
  Tier 4: Live LLM Tests (Optional live query to OpenRouter/DeepSeek) -- opt-in via --live

Usage:
  python scripts/test_agent.py          # Runs Tiers 1, 2, 3 (Zero Credits)
  python scripts/test_agent.py --unit   # Runs Tier 1 only
  python scripts/test_agent.py --mcp    # Runs Tier 2 only
  python scripts/test_agent.py --mock   # Runs Tier 3 only
  python scripts/test_agent.py --live   # Runs Tier 4 (Requires active OPENAI_API_KEY)
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

# Ensure project root is in python path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from agent.config import (
    VALID_PERSONAS,
    VALID_SECTORS,
    validate_config,
    validate_persona,
    validate_sector,
)
from agent.core import FinancialAgent
from agent.mcp_client import MCPClient
from agent.personas import (
    BASE_INSTRUCTIONS,
    EQUITY_ANALYST_PROMPT,
    MF_ANALYST_PROMPT,
    PE_ANALYST_PROMPT,
    build_system_prompt,
    get_sector_guidance,
)
from agent.response import AgentResponse, DataSourceRecord


def check(label: str, condition: bool, detail: str = "") -> bool:
    status = "PASS" if condition else "FAIL"
    msg = f"  [{status}] {label}"
    if detail:
        msg += f"  --  {detail}"
    print(msg)
    return condition


# =====================================================================
# TIER 1: UNIT TESTS (Zero Credits, Offline)
# =====================================================================
def run_tier1_unit_tests() -> tuple[int, int]:
    print("\n" + "=" * 70)
    print("  TIER 1: Unit Tests (Configs, Prompts, Boundaries, Models)")
    print("=" * 70)
    passed = 0
    failed = 0

    def track(ok: bool):
        nonlocal passed, failed
        if ok:
            passed += 1
        else:
            failed += 1

    # 1.1 Config Matrix (All 9 combinations must validate)
    print("\n1.1 Testing 9 Persona x Sector Combinations...")
    combos_valid = True
    combo_count = 0
    for p in VALID_PERSONAS:
        for s in VALID_SECTORS:
            vp, vs = validate_config(p, s)
            if vp != p or vs != s:
                combos_valid = False
            combo_count += 1
    track(check(f"All 9 valid combinations pass ({combo_count} combos)", combos_valid and combo_count == 9))

    # 1.2 Invalid Config Rejection
    print("\n1.2 Testing Rejection of Invalid Configurations...")
    invalid_persona_rejected = False
    try:
        validate_persona("crypto_degen")
    except ValueError:
        invalid_persona_rejected = True
    track(check("Rejects invalid persona ('crypto_degen')", invalid_persona_rejected))

    invalid_sector_rejected = False
    try:
        validate_sector("biotech")
    except ValueError:
        invalid_sector_rejected = True
    track(check("Rejects invalid sector ('biotech')", invalid_sector_rejected))

    # 1.3 System Prompt Assembly
    print("\n1.3 Testing System Prompt Assembly...")
    assembled_prompts_ok = True
    for p in VALID_PERSONAS:
        for s in VALID_SECTORS:
            prompt = build_system_prompt(p, s)
            if len(prompt) < 500:
                assembled_prompts_ok = False
    track(check("System prompt builds successfully for all 9 combos", assembled_prompts_ok))

    # 1.4 Persona Vocabulary & Grounding Constraints
    print("\n1.4 Testing Persona Vocabulary & Anti-Hallucination Directives...")
    mf_prompt = build_system_prompt("mf_analyst", "tech")
    track(check("MF Analyst contains 'benchmark-relative' framing", "benchmark-relative" in mf_prompt.lower()))
    track(check("MF Analyst contains 'core holding' vocabulary", "core holding" in mf_prompt.lower()))
    track(check("MF Analyst forbids inventing external index multiples", "never invent or speculate on external index multiples" in mf_prompt.lower() or "never invent numerical levels" in mf_prompt.lower()))

    eq_prompt = build_system_prompt("equity_analyst", "tech")
    track(check("Equity Analyst contains rating conviction ('Buy / Outperform')", "buy / outperform" in eq_prompt.lower()))
    track(check("Equity Analyst contains 'margin expansion' vocabulary", "margin expansion" in eq_prompt.lower()))
    track(check("Equity Analyst forbids fabricating Street consensus price targets", "never fabricate third-party street consensus price targets" in eq_prompt.lower()))

    pe_prompt = build_system_prompt("pe_analyst", "logistics")
    track(check("PE Analyst contains 'LBO' / 'take-private' vocabulary", "lbo" in pe_prompt.lower() or "take-private" in pe_prompt.lower()))
    track(check("PE Analyst uses FCF conversion as proxy for capex/reinvestment", "fcf / ebitda" in pe_prompt.lower() or "cash conversion" in pe_prompt.lower()))
    track(check("PE Analyst contains 'debt capacity' / 'exit multiple'", "debt capacity" in pe_prompt.lower()))

    # 1.5 Lean Sector Focus
    print("\n1.5 Testing Lean Sector Guidance (No Baked Facts)...")
    tech_sec = get_sector_guidance("tech")
    retail_sec = get_sector_guidance("retail")
    logistics_sec = get_sector_guidance("logistics")
    track(check("Tech guidance guides themes without hardcoded numbers", "saas" in tech_sec.lower() and "query only" in tech_sec.lower()))
    track(check("Retail guidance guides themes without hardcoded numbers", "omnichannel" in retail_sec.lower() and "query only" in retail_sec.lower()))
    track(check("Logistics guidance guides themes without hardcoded numbers", "route density" in logistics_sec.lower() and "query only" in logistics_sec.lower()))

    # 1.6 AgentResponse Model
    print("\n1.6 Testing Structured Response Model...")
    sample_resp = AgentResponse(
        answer="Sample institutional narrative.",
        persona="pe_analyst",
        sector="logistics",
        companies_referenced=["FDX", "UPS"],
        tools_used=["get_company_details"],
        data_sources=[
            DataSourceRecord(
                company="FDX",
                metric_or_event="FY2024 EBITDA & Debt-to-EBITDA",
                source="FedEx FY2024 10-K",
                source_url="https://www.sec.gov/edgar",
            )
        ],
        confidence="high",
    )
    resp_dict = sample_resp.to_dict()
    resp_json = sample_resp.to_json()
    track(check("AgentResponse serializes to valid dict", isinstance(resp_dict, dict) and resp_dict["persona"] == "pe_analyst"))
    track(check("AgentResponse serializes to valid JSON string", '"confidence": "high"' in resp_json))

    return passed, failed


# =====================================================================
# TIER 2: MCP PROTOCOL INTEGRATION TESTS (Zero Credits, Stdio)
# =====================================================================
async def run_tier2_mcp_tests() -> tuple[int, int]:
    print("\n" + "=" * 70)
    print("  TIER 2: MCP Stdio Protocol Tests (Client Lifecycle & Tool Execution)")
    print("=" * 70)
    passed = 0
    failed = 0

    def track(ok: bool):
        nonlocal passed, failed
        if ok:
            passed += 1
        else:
            failed += 1

    client = MCPClient()
    try:
        print("\n2.1 Connecting to MCP server via stdio transport...")
        await client.start()
        track(check("MCP Client connected and handshake complete", client.session is not None))

        # 2.2 List and translate tools
        print("\n2.2 Discovering MCP Tools and Translating to LLM Schemas...")
        tools = await client.list_tools()
        track(check(f"Discovered {len(tools)} tools from MCP server", len(tools) == 7))

        llm_tools = await client.get_tools_for_llm()
        track(check("Translated tools to OpenAI function schema format", len(llm_tools) == 7 and llm_tools[0]["type"] == "function"))
        track(check("First tool schema has valid 'function' mapping", "name" in llm_tools[0]["function"] and "parameters" in llm_tools[0]["function"]))

        # 2.3 Live Tool Calls
        print("\n2.3 Calling MCP Tools over Stdio JSON-RPC...")
        sec_res = await client.call_tool("list_sectors", {})
        track(check("list_sectors returned 3 sectors", isinstance(sec_res, list) and len(sec_res) == 3))

        nvda_res = await client.call_tool("get_company_details", {"ticker": "NVDA"})
        track(check("get_company_details('NVDA') returned company profile", "company" in nvda_res and nvda_res["company"]["ticker"] == "NVDA"))
        track(check("NVDA headcount is present (stress test data)", nvda_res["company"].get("headcount") is not None))

        # 2.4 Out-of-Scope Tool Call
        print("\n2.4 Calling Out-of-Scope Company ('TSLA')...")
        tsla_res = await client.call_tool("get_company_details", {"ticker": "TSLA"})
        track(check("TSLA returns clear 'not found' error", "error" in tsla_res and "not found" in str(tsla_res["error"]).lower()))

        # 2.5 Provenance Extraction Verification
        print("\n2.5 Testing Provenance Extraction from MCP Outputs...")
        sources, tickers = MCPClient.extract_provenance("get_company_details", {"ticker": "NVDA"}, nvda_res)
        track(check("Extracted ticker 'NVDA' directly from MCP tool result", "NVDA" in tickers))
        track(check(f"Extracted {len(sources)} source records with URLs directly from DB records", len(sources) > 0 and all("source_url" in s for s in sources)))

        # Provenance for out-of-scope company should not register ticker as available
        _, tsla_tickers = MCPClient.extract_provenance("get_company_details", {"ticker": "TSLA"}, tsla_res)
        track(check("Out-of-scope 'TSLA' is not recorded as an available ticker", "TSLA" not in tsla_tickers))

    finally:
        await client.stop()
        track(check("MCP Client session cleanly closed", client.session is None))

    return passed, failed


# =====================================================================
# TIER 3: MOCK AGENT LOOP TESTS (Zero Credits, Deterministic)
# =====================================================================
class MockLLMMessage:
    def __init__(self, content: str = "", tool_calls: list[Any] = None):
        self.content = content
        self.tool_calls = tool_calls or []

    def model_dump(self):
        return {
            "role": "assistant",
            "content": self.content,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in self.tool_calls
            ],
        }


class MockToolCallFunction:
    def __init__(self, name: str, arguments: str):
        self.name = name
        self.arguments = arguments


class MockToolCall:
    def __init__(self, call_id: str, name: str, arguments: dict[str, Any]):
        self.id = call_id
        self.type = "function"
        self.function = MockToolCallFunction(name, json.dumps(arguments))


class MockChatCompletionResponse:
    def __init__(self, message: MockLLMMessage):
        self.choices = [type("Choice", (), {"message": message})()]


class ScriptedMockLLM:
    """Simulates multi-step LLM responses to test FinancialAgent tool calling loop."""

    def __init__(self, scripted_steps: list[MockLLMMessage]):
        self.scripted_steps = list(scripted_steps)
        self.step_index = 0
        self.chat = type("Chat", (), {"completions": type("Completions", (), {"create": self._create})()})()

    async def _create(self, **kwargs):
        if self.step_index < len(self.scripted_steps):
            resp = MockChatCompletionResponse(self.scripted_steps[self.step_index])
            self.step_index += 1
            return resp
        # Fallback to final answer
        return MockChatCompletionResponse(MockLLMMessage("Final analysis completed."))


async def run_tier3_mock_agent_tests() -> tuple[int, int]:
    print("\n" + "=" * 70)
    print("  TIER 3: Mock Agent Tests (Multi-Step Tool Calling & Provenance Loop)")
    print("=" * 70)
    passed = 0
    failed = 0

    def track(ok: bool):
        nonlocal passed, failed
        if ok:
            passed += 1
        else:
            failed += 1

    # 3.1 Test Headcount / Hiring Signal Stress Test Loop
    print("\n3.1 Testing Headcount/Hiring Stress Test Tool Loop with Live MCP Server...")
    step1_tool = MockToolCall("call_1", "get_company_details", {"ticker": "NVDA"})
    step2_tool = MockToolCall("call_2", "search_news_events", {"ticker": "NVDA", "event_type": "hiring"})
    final_text = "NVIDIA's latest verified headcount is approximately 29,600 employees with positive YoY hiring trends."

    mock_llm = ScriptedMockLLM([
        MockLLMMessage(content="", tool_calls=[step1_tool]),
        MockLLMMessage(content="", tool_calls=[step2_tool]),
        MockLLMMessage(content=final_text, tool_calls=[]),
    ])

    async with FinancialAgent(
        persona="equity_analyst",
        sector="tech",
        llm_client=mock_llm,
    ) as agent:
        resp = await agent.query("What's the most recent headcount or hiring signal for NVDA?")

        track(check("Agent returned AgentResponse instance", isinstance(resp, AgentResponse)))
        track(check("Persona is 'equity_analyst'", resp.persona == "equity_analyst"))
        track(check("Sector is 'tech'", resp.sector == "tech"))
        track(check("Tools used includes 'get_company_details' and 'search_news_events'", "get_company_details" in resp.tools_used and "search_news_events" in resp.tools_used))
        track(check("Companies referenced contains 'NVDA'", "NVDA" in resp.companies_referenced))
        track(check(f"Data sources extracted from live DB ({len(resp.data_sources)} records)", len(resp.data_sources) > 0))
        track(check("Data sources have valid source URLs", any("sec.gov" in s.source_url or "http" in s.source_url for s in resp.data_sources)))
        track(check("Confidence is 'high'", resp.confidence == "high"))

    # 3.2 Test Out-of-Scope Company Test Loop
    print("\n3.2 Testing Out-of-Scope Company Tool Loop ('TSLA')...")
    step_oos_tool = MockToolCall("call_oos", "get_company_details", {"ticker": "TSLA"})
    final_oos_text = "I have checked our database coverage for TSLA. TSLA is not found in our coverage universe for the Tech sector."

    mock_llm_oos = ScriptedMockLLM([
        MockLLMMessage(content="", tool_calls=[step_oos_tool]),
        MockLLMMessage(content=final_oos_text, tool_calls=[]),
    ])

    async with FinancialAgent(
        persona="mf_analyst",
        sector="tech",
        llm_client=mock_llm_oos,
    ) as agent_oos:
        resp_oos = await agent_oos.query("What do you think about TSLA?")

        track(check("Out-of-scope response generated", "not found" in resp_oos.answer.lower()))
        track(check("Out-of-scope company TSLA is NOT listed in companies_referenced", "TSLA" not in resp_oos.companies_referenced))
        track(check("Confidence is 'medium' for out-of-scope query", resp_oos.confidence == "medium"))

    # 3.3 Test PE Analyst Buyout Target Query
    print("\n3.3 Testing PE Analyst Buyout Target Query Loop...")
    step_pe_tool = MockToolCall("call_pe", "query_financials", {"sector": "logistics", "metric": "debt_to_ebitda", "order": "asc"})
    final_pe_text = "Based on debt-to-EBITDA and cash generation, several logistics companies present viable LBO candidates."

    mock_llm_pe = ScriptedMockLLM([
        MockLLMMessage(content="", tool_calls=[step_pe_tool]),
        MockLLMMessage(content=final_pe_text, tool_calls=[]),
    ])

    async with FinancialAgent(
        persona="pe_analyst",
        sector="logistics",
        llm_client=mock_llm_pe,
    ) as agent_pe:
        resp_pe = await agent_pe.query("Which companies look like attractive buyout targets based on leverage capacity?")

        track(check("PE persona correctly set", resp_pe.persona == "pe_analyst"))
        track(check("Logistics sector correctly set", resp_pe.sector == "logistics"))
        track(check("query_financials invoked", "query_financials" in resp_pe.tools_used))
        track(check("Data sources extracted from ranking query", len(resp_pe.data_sources) > 0))

    return passed, failed


# =====================================================================
# TIER 4: LIVE LLM TESTS (Optional / Opt-in via --live)
# =====================================================================
async def run_tier4_live_tests() -> tuple[int, int]:
    print("\n" + "=" * 70)
    print("  TIER 4: Live LLM Tests (OpenRouter / DeepSeek)")
    print("=" * 70)
    passed = 0
    failed = 0

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or api_key.startswith("your_") or len(api_key) < 10:
        print("\n  [SKIP] OPENAI_API_KEY not found or using placeholder in .env.")
        print("         To run live tests, set OPENAI_API_KEY in .env and run:")
        print("         python scripts/test_agent.py --live\n")
        return 0, 0

    print(f"\nLive API Key detected! Running live query with model {os.getenv('OPENAI_MODEL', 'default')}...")

    def track(ok: bool):
        nonlocal passed, failed
        if ok:
            passed += 1
        else:
            failed += 1

    try:
        async with FinancialAgent(
            persona="pe_analyst",
            sector="logistics",
        ) as agent:
            print("\nSending live query: 'Which companies in logistics look like attractive buyout targets?'...")
            resp = await agent.query("Which companies in this sector look like attractive buyout targets based on the data you have?")

            print("\n--- Live Agent Response ---")
            print(f"Persona: {resp.persona} | Sector: {resp.sector}")
            print(f"Tools Used: {resp.tools_used}")
            print(f"Companies Referenced: {resp.companies_referenced}")
            print(f"Data Sources: {len(resp.data_sources)}")
            print(f"Confidence: {resp.confidence}")
            print(f"\nNarrative excerpt:\n{resp.answer[:400]}...\n")

            track(check("Live query produced non-empty answer", len(resp.answer) > 100))
            track(check("Live query used MCP tools", len(resp.tools_used) > 0))
            track(check("Live query referenced companies", len(resp.companies_referenced) > 0))
            track(check("Live query captured data sources", len(resp.data_sources) > 0))
    except Exception as e:
        print(f"\n  [ERROR] Live test failed with error: {e}")
        failed += 1

    return passed, failed


# =====================================================================
# MAIN RUNNER
# =====================================================================
async def main():
    args = sys.argv[1:]
    run_all = len(args) == 0 or "--all" in args
    run_unit = run_all or "--unit" in args
    run_mcp = run_all or "--mcp" in args
    run_mock = run_all or "--mock" in args
    run_live = "--live" in args

    total_passed = 0
    total_failed = 0

    if run_unit:
        p, f = run_tier1_unit_tests()
        total_passed += p
        total_failed += f

    if run_mcp:
        p, f = await run_tier2_mcp_tests()
        total_passed += p
        total_failed += f

    if run_mock:
        p, f = await run_tier3_mock_agent_tests()
        total_passed += p
        total_failed += f

    if run_live:
        p, f = await run_tier4_live_tests()
        total_passed += p
        total_failed += f

    print("\n" + "=" * 70)
    print(f"  TOTAL TEST RESULTS: {total_passed} passed, {total_failed} failed")
    print("=" * 70)

    if total_failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
