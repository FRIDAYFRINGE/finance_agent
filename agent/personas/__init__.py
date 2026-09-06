"""System prompt builder for Financial Analyst personas and sector guidance."""

from agent.config import validate_config
from agent.personas.base import BASE_INSTRUCTIONS
from agent.personas.equity_analyst import EQUITY_ANALYST_PROMPT
from agent.personas.mf_analyst import MF_ANALYST_PROMPT
from agent.personas.pe_analyst import PE_ANALYST_PROMPT
from agent.personas.sectors import get_sector_guidance

PERSONA_PROMPTS = {
    "mf_analyst": MF_ANALYST_PROMPT,
    "equity_analyst": EQUITY_ANALYST_PROMPT,
    "pe_analyst": PE_ANALYST_PROMPT,
}


def build_system_prompt(persona: str, sector: str) -> str:
    """Assembles the complete system prompt for the specified persona and sector.
    
    Combines:
    1. Persona-specific analytical directives and evaluation heuristics.
    2. Lean sector analytical focus (without hardcoded facts).
    3. Base grounding instructions, minimal tool selection rules, and anti-hallucination constraints.
    """
    valid_persona, valid_sector = validate_config(persona, sector)

    persona_prompt = PERSONA_PROMPTS[valid_persona].strip()
    sector_guidance = get_sector_guidance(valid_sector).strip()
    base_instructions = BASE_INSTRUCTIONS.strip()

    return (
        f"{persona_prompt}\n\n"
        f"---\n\n"
        f"{sector_guidance}\n\n"
        f"---\n\n"
        f"{base_instructions}"
    )


__all__ = [
    "BASE_INSTRUCTIONS",
    "MF_ANALYST_PROMPT",
    "EQUITY_ANALYST_PROMPT",
    "PE_ANALYST_PROMPT",
    "PERSONA_PROMPTS",
    "get_sector_guidance",
    "build_system_prompt",
]
