"""Sector guidance instructions.

Guides what analytical aspects, operational levers, and key metrics to examine
for each sector without baking any hardcoded facts, numbers, tailwinds, or company
data into the prompt. All factual data must come from live MCP queries.
"""

SECTOR_GUIDANCE = {
    "tech": """## Current Sector Mandate: Technology
You are currently analyzing the Technology sector.
- **Analytical Focus Areas**:
  * Differentiate between SaaS/cloud enterprise software, semiconductor hardware, and consumer hardware business models.
  * Evaluate gross margin durability and operating leverage across fiscal years.
  * Examine recurring revenue stability vs. cyclical hardware/semiconductor demand.
  * Assess balance sheet cash cushions and R&D reinvestment efficiency.
- **Data Boundary**: Query ONLY companies and data in the 'tech' sector using your MCP tools. Retrieve live facts, tailwinds, and sector averages dynamically via `get_sector_overview(sector='tech')` and related tools.""",

    "retail": """## Current Sector Mandate: Retail
You are currently analyzing the Retail sector.
- **Analytical Focus Areas**:
  * Evaluate omnichannel, discount retail, e-commerce, and specialized retail models.
  * Analyze operating margins, inventory efficiency, and gross margin defense against cost inflation.
  * Assess consumer spending sensitivity, same-store performance dynamics, and store network stability.
  * Examine debt levels and free cash flow generation across the retail landscape.
- **Data Boundary**: Query ONLY companies and data in the 'retail' sector using your MCP tools. Retrieve live facts, tailwinds, and sector averages dynamically via `get_sector_overview(sector='retail')` and related tools.""",

    "logistics": """## Current Sector Mandate: Logistics
You are currently analyzing the Logistics sector.
- **Analytical Focus Areas**:
  * Evaluate contract warehousing, package delivery, LTL freight, and freight brokerage business models.
  * Analyze capital intensity (fleet, hub facilities) and examine FCF conversion as a proxy for reinvestment demands.
  * Evaluate cyclical freight demand, volume trends, route density, and operating leverage.
  * Scrutinize leverage capacity (`debt_to_ebitda`, total debt) and cash generation for debt service or buyout financing.
- **Data Boundary**: Query ONLY companies and data in the 'logistics' sector using your MCP tools. Retrieve live facts, tailwinds, and sector averages dynamically via `get_sector_overview(sector='logistics')` and related tools.""",
}


def get_sector_guidance(sector: str) -> str:
    """Returns lean sector analytical guidance for the specified sector."""
    normalized = sector.lower().strip()
    if normalized not in SECTOR_GUIDANCE:
        raise ValueError(f"Unknown sector '{sector}'. Expected one of: {list(SECTOR_GUIDANCE.keys())}")
    return SECTOR_GUIDANCE[normalized]
