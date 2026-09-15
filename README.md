# Financial Analyst AI Agent (MCP-Grounded Dual Interface)

A financial AI agent featuring **3 configurable analytical personas**, **3 switchable industry sectors**, and a **live SQLite database** queried strictly through the **Model Context Protocol (MCP)**. Exposed via both a **FastAPI REST API** and an interactive **Streamlit Web UI** sharing the exact same agent core.

> **Formal Verification Audit**: Full benchmark evaluation report at [`developer/reports/evaluation_report.md`](developer/reports/evaluation_report.md).

---

## 1. System Architecture & The MCP Protocol Boundary

The agent adheres to a strict protocol separation: **neither the agent, API, nor UI ever imports `sqlite3` or accesses the database directly**. All data retrieval occurs via JSON-RPC tool calls over an MCP stdio subprocess.

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                            DUAL INTERFACES                                  │
│       Streamlit Web UI (Human)         │      FastAPI Endpoint (REST)       │
│       http://localhost:8501            │      http://localhost:8000         │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ calls agent.query(...)
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                       SHARED AGENT CORE (agent/core.py)                     │
│  FinancialAgent(persona, sector)                                            │
│   ├── System Prompt: Analytical persona lens + lean sector guidance         │
│   ├── Tool Calling Loop: Translates MCP tools into OpenAI function schemas  │
│   └── Provenance Extractor: Extracts authentic filing URLs from DB records  │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ tool calls via stdio (JSON-RPC)
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                     MCP TOOL SERVER (mcp_server/server.py)                  │
│  MCPServer over stdio transport                                             │
│   ├── 7 Registered Tools (whitelist-validated SQL queries)                  │
│   └── Read-only connection: data/financial_agent.db?mode=ro                │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ read-only SQL
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         SQLITE DATABASE (5 TABLES)                          │
│     sectors  │  companies  │  financials  │  valuations  │  news_events     │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Analytical Personas & Decision Lenses

The same underlying database records produce distinct reasoning frameworks across the 3 personas:

| Persona | Config Identifier | Analytical Lens & Vocabulary | Primary Decision Heuristics |
| :--- | :--- | :--- | :--- |
| **Mutual Fund Analyst** | `mf_analyst` | Long-only, capital preservation, sustainable compounders, benchmark-relative sector comparisons. | *"Core holding"*, *"tactical overweight"*, *"avoid"*, balance sheet leverage, durability. |
| **Equity Research Analyst** | `equity_analyst` | Fundamentals-driven, revenue momentum, gross/operating margin bridges, earnings quality. | *"Buy / Outperform"*, *"Hold / Neutral"*, *"Sell / Underperform"*, operating leverage, P/E. |
| **Private Equity Analyst** | `pe_analyst` | Buyout/LBO lens, cash flow conversion (`FCF / EBITDA`), operational margin expansion, exit multiples. | *"Take-private"*, *"debt capacity"*, operational levers, 3–5 yr exit multiples. |

---

## 3. Sectors & Coverage Universe (21 Companies)

Data was compiled from SEC Form 10-K filings, official press releases, and Yahoo Finance across 3 sectors (7 companies each, 150 total records):
* **Technology**: Apple (`AAPL`), NVIDIA (`NVDA`), Microsoft (`MSFT`), Alphabet (`GOOG`), Salesforce (`CRM`), Adobe (`ADBE`), Intel (`INTC`).
* **Retail**: Walmart (`WMT`), Amazon (`AMZN`), Target (`TGT`), Costco (`COST`), Home Depot (`HD`), Lowe's (`LOW`), Dollar General (`DG`).
* **Logistics**: United Parcel Service (`UPS`), FedEx (`FDX`), J.B. Hunt (`JBHT`), Expeditors (`EXPD`), XPO (`XPO`), C.H. Robinson (`CHRW`), GXO Logistics (`GXO`).

---

## 4. SQLite Schema Decisions & Sourcing

The database (`data/financial_agent.db`) employs **5 normalized tables**:
1. `sectors`: Qualitative market context and dynamic aggregate anchors.
2. `companies`: Static corporate profiles, headquarters, exchange, and headcount data (e.g. NVDA: 29,600 employees, +13.0% YoY).
3. `financials`: Fiscal year accounting metrics (Revenue, Gross Profit, Operating Income, EBITDA, Net Income, OCF, FCF, Debt, Cash). Sourced from audited **SEC Form 10-K** filings.
4. `valuations`: Curated Q4 2024 valuation snapshot (Market Cap, P/E TTM/Forward, EV/EBITDA, Price, Dividend Yield). Yahoo Finance quote URLs are retained as source references; these live endpoints do not independently prove the historical snapshot date.
5. `news_events`: Material corporate events, restructuring, guidance shifts, and hiring signals.

### Key Design Rationales:
* **Separation of Accounting vs. Market Multiples**: Financial statements reflect audited historical periods (`FY2023`, `FY2024`), whereas valuations represent point-in-time trading prices (anchored to a curated Q4 2024 snapshot). Separating them avoids denormalization anomalies.
* **SQL Injection Prevention**: The MCP server strictly validates metric names against an internal column whitelist (`mcp_server/config.py`) before query assembly.
* **Authentic Provenance Traceability**: Preserves direct source links returned dynamically in `AgentResponse.data_sources`: financial accounting metrics link directly to SEC EDGAR Form 10-K filing accessions, corporate news events link to attached company press releases and SEC disclosures, and valuation records preserve Yahoo Finance reference URLs (subject to the Q4 2024 snapshot caveat below).

---

## 5. Quickstart & Setup Guide

### Prerequisites
* Python 3.11+
* OpenRouter API key (or compatible OpenAI-format endpoint)

### 1. Clone & Install Dependencies
```bash
git clone https://github.com/FRIDAYFRINGE/finance_agent.git
cd finance_agent

python -m venv venv
# Windows:
.\venv\Scripts\activate
# Linux / macOS:
source venv/bin/activate

pip install -r requirements.txt
```

### 2. Configure Environment Variables
Copy `.env.example` to `.env` and provide your API key:
```bash
cp .env.example .env
```
```ini
OPENAI_API_KEY=sk-or-v1-...
OPENAI_BASE_URL=https://openrouter.ai/api/v1
OPENAI_MODEL=z-ai/glm-5.3-flash
```
*(Default tested model is `z-ai/glm-5.3-flash`; `deepseek/deepseek-v4-pro-0813` is also supported).*

### 3. Rebuild Database (Optional Reproducibility Check)
A pre-populated SQLite database is included at `data/financial_agent.db`. To verify deterministic rebuild from raw CSVs:
```bash
python scripts/build_db.py --rebuild
```

---

## 6. Running the Dual Interface

The unified launcher `run.py` controls both services:

```bash
# Start both FastAPI (:8000) and Streamlit (:8501) concurrently:
python run.py both

# Start REST API service only:
python run.py api

# Start Streamlit Web UI only:
python run.py ui
```
* **Interactive Web Dashboard**: Navigate to `http://localhost:8501`.
* **API Swagger Documentation**: Navigate to `http://localhost:8000/docs`.

---

## 7. Example API Request & Programmatic Response

```bash
curl -X POST "http://127.0.0.1:8000/query" \
     -H "Content-Type: application/json" \
     -d '{
       "query": "Walk me through the margin profile of logistics companies — who is improving and who is under pressure?",
       "persona": "equity_analyst",
       "sector": "logistics"
     }'
```

### Structured JSON Response Schema (`AgentResponse`):
```json
{
  "answer": "Based on audited SEC 10-K filings, XPO demonstrated meaningful operating margin expansion from 5.7% in FY23 to 8.2% in FY24 (+250 bps) driven by LTL network density and yield discipline, while GXO experienced operating margin compression from 3.3% to 1.9% following acquisition and integration costs...",
  "persona": "equity_analyst",
  "sector": "logistics",
  "companies_referenced": ["GXO", "UPS", "FDX", "JBHT", "EXPD", "XPO", "CHRW"],
  "tools_used": ["get_sector_overview", "list_companies", "query_financials", "get_company_details"],
  "data_sources": [
    {
      "company": "XPO",
      "metric_or_event": "Operating Margin: 8.2% (FY24) vs 5.7% (FY23), Revenue: $8,072M",
      "source": "SEC 10-K FY2024",
      "source_url": "https://www.sec.gov/Archives/edgar/data/1166003/000116600325000014/xpo-20241231.htm"
    }
  ],
  "confidence": "high",
  "disclaimer": "AI-generated financial analysis for informational purposes only. Not investment advice."
}
```

---
