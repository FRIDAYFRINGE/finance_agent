import argparse
from pathlib import Path
import sys
from unittest.mock import AsyncMock, patch

# Ensure UTF-8 output encoding on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Ensure project root is in python path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient

from agent.config import VALID_PERSONAS, VALID_SECTORS
from agent.response import AgentResponse, DataSourceRecord, DEFAULT_DISCLAIMER
from api.main import app


def run_tests(is_live: bool = False):
    print("=" * 70)
    print(f"🧪 Running FastAPI Test Suite (Mode: {'LIVE OPENROUTER' if is_live else 'ZERO-CREDIT OFFLINE'})")
    print("=" * 70)

    passed = 0
    total = 0

    with TestClient(app) as client:

        # Test 1: GET /health
        total += 1
        print(f"\n[Test {total}] GET /health (Readiness Check)...")
        resp = client.get("/health")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data["status"] == "healthy", f"Status not healthy: {data}"
        assert data["mcp_server_connected"] is True, f"MCP not connected: {data}"
        assert data["tools_available"] == 7, f"Expected 7 tools, got: {data['tools_available']}"
        print("  ✅ /health returned 200 with 7 MCP tools connected.")
        passed += 1

        # Test 2: GET /config
        total += 1
        print(f"\n[Test {total}] GET /config (Metadata Discovery)...")
        resp = client.get("/config")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        cfg = resp.json()
        persona_ids = [p["id"] for p in cfg["personas"]]
        sector_ids = [s["id"] for s in cfg["sectors"]]
        assert set(persona_ids) == set(VALID_PERSONAS), f"Personas mismatch: {persona_ids}"
        assert set(sector_ids) == set(VALID_SECTORS), f"Sectors mismatch: {sector_ids}"
        print(f"  ✅ /config returned {len(persona_ids)} personas and {len(sector_ids)} sectors.")
        passed += 1

        # Test 3: POST /query Input Validation Rejections (422)
        total += 1
        print(f"\n[Test {total}] POST /query Input Validation (422 Rejections)...")
        
        # 3a: Invalid persona
        r_bad_persona = client.post(
            "/query",
            json={"query": "Test query", "persona": "crypto_analyst", "sector": "tech"},
        )
        assert r_bad_persona.status_code == 422, f"Expected 422, got {r_bad_persona.status_code}"
        
        # 3b: Invalid sector
        r_bad_sector = client.post(
            "/query",
            json={"query": "Test query", "persona": "pe_analyst", "sector": "biotech"},
        )
        assert r_bad_sector.status_code == 422, f"Expected 422, got {r_bad_sector.status_code}"

        # 3c: Empty query
        r_empty_query = client.post(
            "/query",
            json={"query": "", "persona": "pe_analyst", "sector": "tech"},
        )
        assert r_empty_query.status_code == 422, f"Expected 422, got {r_empty_query.status_code}"

        # 3d: Missing fields
        r_missing = client.post(
            "/query",
            json={"persona": "pe_analyst"},
        )
        assert r_missing.status_code == 422, f"Expected 422, got {r_missing.status_code}"

        print("  ✅ All 4 invalid requests correctly rejected with 422 Unprocessable Content.")
        passed += 1

        # Test 4: CORS Options Header Check
        total += 1
        print(f"\n[Test {total}] OPTIONS /query (CORS Headers Check)...")
        cors_resp = client.options(
            "/query",
            headers={
                "Origin": "http://localhost:8501",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert cors_resp.status_code == 200, f"Expected 200 on OPTIONS, got {cors_resp.status_code}"
        assert "access-control-allow-origin" in cors_resp.headers, "Missing CORS allow-origin header"
        assert cors_resp.headers["access-control-allow-origin"] == "*", "CORS origin mismatch"
        print("  ✅ CORS pre-flight response returned valid headers.")
        passed += 1

        # Test 5: Assignment-Mandated POST /query Structure (instructions.md lines 78-82)
        total += 1
        print(f"\n[Test {total}] POST /query Assignment Mandate Structure...")
        test_payload = {
            "query": "Walk me through the margin profile of the companies in your data — who's improving and who's under pressure?",
            "persona": "equity_analyst",
            "sector": "logistics",
        }

        if is_live:
            print("  Executing live request through OpenRouter...")
            resp = client.post("/query", json=test_payload)
            assert resp.status_code == 200, f"Live query failed ({resp.status_code}): {resp.text}"
            res_data = resp.json()
        else:
            # Zero-credit mock mode
            mock_response = AgentResponse(
                answer=(
                    "Based on FY2023–FY2024 financials retrieved from SEC 10-K filings, "
                    "operating margins in Logistics reflect bifurcation. GXO improved operating margins "
                    "from 4.1% to 4.5%, while UPS faced margin compression from 10.9% to 8.2%."
                ),
                persona="equity_analyst",
                sector="logistics",
                companies_referenced=["GXO", "UPS", "FDX"],
                tools_used=["get_sector_overview", "compare_companies", "query_financials"],
                data_sources=[
                    DataSourceRecord(
                        company="GXO",
                        metric_or_event="FY2024 Accounting Financials (Revenue, Margins, Debt, FCF)",
                        source="SEC 10-K FY2024",
                        source_url="https://www.sec.gov/ix?doc=/Archives/edgar/data/1852244/000185224425000015/gxo-20241231.htm",
                    ),
                    DataSourceRecord(
                        company="UPS",
                        metric_or_event="FY2024 Accounting Financials (Revenue, Margins, Debt, FCF)",
                        source="SEC 10-K FY2024",
                        source_url="https://www.sec.gov/ix?doc=/Archives/edgar/data/1090727/000109072725000014/ups-20241231.htm",
                    ),
                ],
                confidence="high",
                disclaimer=DEFAULT_DISCLAIMER,
            )
            with patch("agent.core.FinancialAgent.query", new_callable=AsyncMock) as mock_query:
                mock_query.return_value = mock_response
                resp = client.post("/query", json=test_payload)
                assert resp.status_code == 200, f"Mock query failed: {resp.text}"
                res_data = resp.json()

        # Contract assertions per instructions.md lines 78-82
        assert isinstance(res_data["answer"], str) and len(res_data["answer"]) > 20
        assert res_data["persona"] == "equity_analyst"
        assert res_data["sector"] == "logistics"
        assert isinstance(res_data["companies_referenced"], list)
        assert isinstance(res_data["tools_used"], list)
        assert isinstance(res_data["data_sources"], list)
        assert len(res_data["data_sources"]) > 0
        for src in res_data["data_sources"]:
            assert "company" in src
            assert "metric_or_event" in src
            assert "source" in src
            assert "source_url" in src
            assert src["source_url"].startswith("http")
        assert res_data["confidence"] in ("high", "medium", "low")
        assert "disclaimer" in res_data and len(res_data["disclaimer"]) > 10

        print("  ✅ Structured JSON response verified per instructions.md (lines 78-82):")
        print(f"     • Answer length: {len(res_data['answer'])} chars")
        print(f"     • Companies: {res_data['companies_referenced']}")
        print(f"     • Tools used: {res_data['tools_used']}")
        print(f"     • Verified data sources count: {len(res_data['data_sources'])}")
        print(f"     • Confidence: {res_data['confidence']}")
        passed += 1

        # Test 6: Out-of-Scope Query Behavior via API
        total += 1
        print(f"\n[Test {total}] POST /query Out-of-Scope Company Handling...")
        oos_payload = {
            "query": "What do you think about TSLA?",
            "persona": "mf_analyst",
            "sector": "tech",
        }
        if is_live:
            resp = client.post("/query", json=oos_payload)
            assert resp.status_code == 200
            oos_data = resp.json()
            assert "tsla" not in [c.lower() for c in oos_data["companies_referenced"]]
        else:
            mock_oos_response = AgentResponse(
                answer="I have no data on TSLA in my database. My coverage is limited to 21 curated companies across Tech, Retail, and Logistics.",
                persona="mf_analyst",
                sector="tech",
                companies_referenced=[],
                tools_used=["get_company_details"],
                data_sources=[],
                confidence="medium",
                disclaimer=DEFAULT_DISCLAIMER,
            )
            with patch("agent.core.FinancialAgent.query", new_callable=AsyncMock) as mock_query:
                mock_query.return_value = mock_oos_response
                resp = client.post("/query", json=oos_payload)
                assert resp.status_code == 200
                oos_data = resp.json()
                assert len(oos_data["companies_referenced"]) == 0
                assert oos_data["confidence"] in ("medium", "low")

        print("  ✅ Out-of-scope company handling verified (empty companies_referenced, proper confidence).")
        passed += 1

    print("\n" + "=" * 70)
    print(f"📊 SUMMARY: {passed}/{total} FastAPI Tests Passed (100% Success)")
    print("=" * 70)
    return passed == total


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run FastAPI Test Suite")
    parser.add_argument("--live", action="store_true", help="Execute live OpenRouter test")
    args = parser.parse_args()

    success = run_tests(is_live=args.live)
    sys.exit(0 if success else 1)
