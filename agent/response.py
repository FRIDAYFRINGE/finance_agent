from typing import Any, Literal
from pydantic import BaseModel, Field

DEFAULT_DISCLAIMER = (
    "AI-generated financial analysis for informational purposes only. "
    "Not investment advice. friday!"
)


class DataSourceRecord(BaseModel):
    company: str = Field(description="Company ticker symbol (e.g. 'NVDA', 'FDX')")
    metric_or_event: str = Field(description="Description of metric, event, or filing referenced")
    source: str = Field(description="Originating source document (e.g. 'SEC 10-K FY2024', 'Yahoo Finance')")
    source_url: str = Field(description="Direct URL or archive link to the source document")


class AgentResponse(BaseModel):
    answer: str = Field(
        description="Detailed narrative response reflecting the persona's analytical framework and data grounding"
    )
    persona: str = Field(
        description="The persona that generated the response ('mf_analyst', 'equity_analyst', 'pe_analyst')"
    )
    sector: str = Field(
        description="The sector analyzed ('tech', 'retail', 'logistics')"
    )
    companies_referenced: list[str] = Field(
        default_factory=list,
        description="List of company ticker symbols analyzed or cited in the response"
    )
    tools_used: list[str] = Field(
        default_factory=list,
        description="Names of MCP tools invoked to answer the query"
    )
    data_sources: list[DataSourceRecord] = Field(
        default_factory=list,
        description="Specific source filings, documents, and URLs retrieved directly from MCP tools"
    )
    confidence: Literal["high", "medium", "low"] = Field(
        default="high",
        description="Confidence level based on data availability and coverage"
    )
    disclaimer: str = Field(
        default=DEFAULT_DISCLAIMER,
        description="Regulatory / informational disclaimer"
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return self.model_dump()

    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON string."""
        return self.model_dump_json(indent=indent)
