"""Pydantic request and response models for the Financial Agent REST API."""

from typing import Literal
from pydantic import BaseModel, Field

# Supported literal values matching agent.config
PersonaLiteral = Literal["mf_analyst", "equity_analyst", "pe_analyst"]
SectorLiteral = Literal["tech", "retail", "logistics"]


class QueryRequest(BaseModel):
    """Request payload for analytical screening and financial Q&A."""

    query: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="The financial question or screening mandate.",
        examples=["Which companies in this sector look like attractive buyout targets based on the data you have?"]
    )
    persona: PersonaLiteral = Field(
        ...,
        description="The analytical persona perspective ('mf_analyst', 'equity_analyst', 'pe_analyst').",
        examples=["pe_analyst"]
    )
    sector: SectorLiteral = Field(
        ...,
        description="The target industry sector ('tech', 'retail', 'logistics').",
        examples=["logistics"]
    )


class HealthResponse(BaseModel):
    """Operational readiness check response."""

    status: str = Field(..., description="Service status (e.g., 'healthy')")
    version: str = Field(..., description="API version")
    mcp_server_connected: bool = Field(..., description="Whether persistent MCP subprocess is connected")
    tools_available: int = Field(..., description="Number of discovered MCP tools available")


class ConfigOption(BaseModel):
    """Option metadata for personas or sectors."""

    id: str = Field(..., description="Unique machine-readable identifier")
    name: str = Field(..., description="Human-readable display name")
    description: str = Field(..., description="Analytical scope or sector description")


class ConfigResponse(BaseModel):
    """Configuration discovery response exposing supported personas and sectors."""

    personas: list[ConfigOption] = Field(..., description="Supported analytical personas")
    sectors: list[ConfigOption] = Field(..., description="Supported industry sectors")
