import os
from pathlib import Path
from dotenv import load_dotenv

# > Automatically load environment variables from .env if present
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

# > Valid analytical personas
VALID_PERSONAS = ["mf_analyst", "equity_analyst", "pe_analyst"]

# > Valid industry sectors
VALID_SECTORS = ["tech", "retail", "logistics"]

# > Default LLM Provider Settings (OpenRouter / glm 5.3 flash)
DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "z-ai/glm-5.3-flash")
DEFAULT_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1")
DEFAULT_API_KEY = os.getenv("OPENAI_API_KEY", "")

PERSONA_METADATA = {
    "mf_analyst": {
        "name": "Mutual Fund Analyst",
        "description": "Long-only, benchmark-relative lens focusing on sustainable growth, valuation vs. sector averages, and portfolio fit.",
        "rating_scale": ["core holding", "tactical overweight", "underweight", "avoid"],
    },
    "equity_analyst": {
        "name": "Equity Research Analyst",
        "description": "Fundamentals-driven lens focusing on revenue trends, margin trajectory, earnings quality, and peer multiple comparisons.",
        "rating_scale": ["Buy / Outperform", "Hold / Neutral", "Sell / Underperform"],
    },
    "pe_analyst": {
        "name": "Private Equity Analyst",
        "description": "Owner-operator deal/ops lens focusing on cash flow (EBITDA, FCF), leverage capacity, operational levers, and exit multiples.",
        "rating_scale": ["Attractive target", "Watch", "Pass"],
    },
}

SECTOR_METADATA = {
    "tech": {
        "name": "Technology",
        "description": "Software, semiconductors, enterprise cloud, and hardware.",
    },
    "retail": {
        "name": "Retail",
        "description": "Omnichannel, discount retail, e-commerce, and home improvement.",
    },
    "logistics": {
        "name": "Logistics",
        "description": "Freight forwarding, package delivery, LTL freight, and contract warehousing.",
    },
}


def validate_persona(persona: str) -> str:
    """Validates that the provided persona is supported."""
    if not persona or persona.lower() not in VALID_PERSONAS:
        raise ValueError(
            f"Invalid persona '{persona}'. Must be one of: {', '.join(VALID_PERSONAS)}"
        )
    return persona.lower()


def validate_sector(sector: str) -> str:
    """Validates that the provided sector is supported."""
    if not sector or sector.lower() not in VALID_SECTORS:
        raise ValueError(
            f"Invalid sector '{sector}'. Must be one of: {', '.join(VALID_SECTORS)}"
        )
    return sector.lower()


def validate_config(persona: str, sector: str) -> tuple[str, str]:
    """Validates both persona and sector independently (all 9 combinations valid)."""
    return validate_persona(persona), validate_sector(sector)
