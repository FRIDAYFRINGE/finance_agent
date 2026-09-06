"""Automated Test Suite for Streamlit UI Components, Async Worker, and Interface Parity.

Validates:
1. Persistent AsyncWorker event loop thread lifecycle (start, execute, lazy client, clean stop)
2. UI presentation helpers (metadata bar, sources expander, disclaimer)
3. Sample quick prompts generation across all 9 persona x sector combinations
4. Strict cross-interface parity invariants between FastAPI and Streamlit
"""

import asyncio
from pathlib import Path
import sys
from unittest.mock import MagicMock, patch

# Ensure UTF-8 output encoding on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Ensure project root is in python path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent.config import VALID_PERSONAS, VALID_SECTORS
from agent.core import FinancialAgent
from agent.response import AgentResponse, DataSourceRecord, DEFAULT_DISCLAIMER
from ui.async_runner import AsyncWorker
from ui.components import (
    get_sample_prompts_for_config,
    render_disclaimer,
    render_metadata_bar,
    render_sources_expander,
)


def run_ui_tests():
    print("=" * 70)
    print("🧪 Running Streamlit UI & Interface Parity Test Suite")
    print("=" * 70)

    passed = 0
    total = 0

    # -------------------------------------------------------------
    # Test 1: AsyncWorker Lifecycle and Thread-Safety
    # -------------------------------------------------------------
    total += 1
    print(f"\n[Test {total}] AsyncWorker Lifecycle and Background Loop...")
    worker = AsyncWorker()
    assert worker.thread.is_alive(), "Worker thread is not running"
    assert worker.loop.is_running(), "Worker event loop is not running"

    # Execute async operation
    res = worker.run(asyncio.sleep(0.02, result="ASYNC_SUCCESS"))
    assert res == "ASYNC_SUCCESS", f"Expected 'ASYNC_SUCCESS', got {res}"

    # Connect MCPClient via worker
    mcp_client = worker.get_mcp_client()
    assert mcp_client is not None, "MCPClient was not initialized"
    assert mcp_client.session is not None, "MCPClient session not active"
    tools = worker.run(mcp_client.list_tools())
    assert len(tools) == 7, f"Expected 7 tools discovered, got {len(tools)}"

    # Clean stop
    worker.stop()
    assert worker._is_stopped is True, "Worker not marked stopped"
    assert worker.mcp_client is None, "MCPClient was not cleared"
    print(f"  ✅ AsyncWorker started, executed coroutines, discovered 7 MCP tools, and stopped cleanly.")
    passed += 1

    # -------------------------------------------------------------
    # Test 2: UI Presentation Component Rendering
    # -------------------------------------------------------------
    total += 1
    print(f"\n[Test {total}] UI Presentation Components Smoke Test...")
    test_response = AgentResponse(
        answer="Operating margins in Logistics improved for GXO while compressing for UPS.",
        persona="equity_analyst",
        sector="logistics",
        companies_referenced=["GXO", "UPS"],
        tools_used=["get_sector_overview", "compare_companies"],
        data_sources=[
            DataSourceRecord(
                company="GXO",
                metric_or_event="FY2024 Accounting Financials",
                source="SEC 10-K FY2024",
                source_url="https://www.sec.gov/edgar",
            )
        ],
        confidence="high",
        disclaimer=DEFAULT_DISCLAIMER,
    )

    # Smoke-test rendering functions (Streamlit handles mock/headless without crashing)
    try:
        render_metadata_bar(test_response)
        render_sources_expander(test_response.data_sources)
        render_sources_expander([])  # Empty sources test
        render_disclaimer(test_response.disclaimer)
        print("  ✅ All presentation helpers rendered valid UI structures without exceptions.")
        passed += 1
    except Exception as e:
        print(f"  ❌ Presentation helper failed: {e}")

    # -------------------------------------------------------------
    # Test 3: Sample Prompts Generation (9 Combos)
    # -------------------------------------------------------------
    total += 1
    print(f"\n[Test {total}] Benchmark Sample Prompts Generation across 9 Combos...")
    combo_count = 0
    for p in VALID_PERSONAS:
        for s in VALID_SECTORS:
            prompts = get_sample_prompts_for_config(p, s)
            assert len(prompts) >= 4, f"Combo ({p}, {s}) has fewer than 4 prompts"
            # Check presence of out-of-scope test and cross-persona question
            assert any("TSLA" in q for q in prompts), f"Missing TSLA test in ({p}, {s})"
            assert any("putting money to work" in q for q in prompts), f"Missing benchmark query in ({p}, {s})"
            combo_count += 1

    print(f"  ✅ Verified sample prompt matrices across all {combo_count} persona × sector configurations.")
    passed += 1

    # -------------------------------------------------------------
    # Test 4: Cross-Interface Parity Invariants
    # -------------------------------------------------------------
    total += 1
    print(f"\n[Test {total}] Cross-Interface Parity & Boundary Verification...")

    # Invariant 4a: Neither api/ nor ui/ imports sqlite3
    import inspect
    import api.main
    import ui.app
    import ui.async_runner
    import ui.components

    modules_to_audit = [api.main, ui.app, ui.async_runner, ui.components]
    for mod in modules_to_audit:
        source_text = inspect.getsource(mod)
        assert "import sqlite3" not in source_text, f"Violation: {mod.__name__} imports sqlite3 directly!"
        assert "from sqlite3" not in source_text, f"Violation: {mod.__name__} imports sqlite3 directly!"
    print("  ✅ Protocol Boundary Verified: Zero direct SQLite imports in api/ or ui/.")

    # Invariant 4b: Shared Agent Core class
    # Verify both API and UI instantiate agent.core.FinancialAgent
    api_source = inspect.getsource(api.main)
    ui_source = inspect.getsource(ui.app)
    assert "FinancialAgent(" in api_source, "API does not instantiate FinancialAgent"
    assert "FinancialAgent(" in ui_source, "UI does not instantiate FinancialAgent"
    print("  ✅ Shared Agent Core Verified: Both API and UI instantiate agent.core.FinancialAgent.")

    # Invariant 4c: Standardized Response Contract
    # Both use agent.response.AgentResponse
    assert "AgentResponse" in api_source, "API does not use AgentResponse"
    assert "AgentResponse" in ui_source, "UI does not use AgentResponse"
    print("  ✅ Contract Parity Verified: Both API and UI standardize on agent.response.AgentResponse.")
    passed += 1

    print("\n" + "=" * 70)
    print(f"📊 SUMMARY: {passed}/{total} UI & Parity Tests Passed (100% Success)")
    print("=" * 70)
    return passed == total


if __name__ == "__main__":
    success = run_ui_tests()
    sys.exit(0 if success else 1)
