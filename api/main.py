"""FastAPI entry point for the Financial Analyst AI Agent.

Exposes REST endpoints for programmatic institutional analysis, operational health checks,
and metadata discovery while maintaining the strict MCP protocol boundary.
"""

from contextlib import asynccontextmanager
import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from agent.config import PERSONA_METADATA, SECTOR_METADATA
from agent.core import FinancialAgent
from agent.mcp_client import MCPClient
from agent.response import AgentResponse
from api.models import ConfigOption, ConfigResponse, HealthResponse, QueryRequest

logger = logging.getLogger("api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manages the process-level MCP client lifecycle for the FastAPI service."""
    logger.info("Initializing persistent MCP client for FastAPI process...")
    mcp_client = MCPClient()
    try:
        await mcp_client.start()
        app.state.mcp_client = mcp_client
        logger.info("MCP client connected successfully with %d tools discovered.", len(mcp_client._tools_cache))
    except Exception as e:
        logger.error("Failed to connect MCP client during startup: %s", e)
        app.state.mcp_client = None

    yield

    logger.info("Shutting down MCP client for FastAPI process...")
    if app.state.mcp_client is not None:
        try:
            await app.state.mcp_client.stop()
        except Exception as e:
            logger.warning("Error stopping MCP client during shutdown: %s", e)
        app.state.mcp_client = None


app = FastAPI(
    title="Financial Analyst AI Agent API",
    description=(
        "Dual-interface REST API exposing persona-configurable financial analysis "
        "grounded in live SQLite data through the Model Context Protocol (MCP) and DeepSeek."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Cross-Origin Resource Sharing (CORS) configuration
# Credentials disabled with wildcard origin to adhere strictly to browser security standards
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catches unhandled exceptions and returns a clean, structured JSON error response."""
    logger.exception("Unhandled server error processing %s: %s", request.url.path, exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": f"Internal execution error: {str(exc)}"},
    )


@app.post(
    "/query",
    response_model=AgentResponse,
    status_code=status.HTTP_200_OK,
    summary="Submit Financial Screening / Q&A Query",
    description=(
        "Accepts a query, analytical persona, and target industry sector. "
        "Executes live MCP tool queries against the database and returns "
        "a grounded, structured AgentResponse."
    ),
)
async def query_endpoint(req: QueryRequest, request: Request) -> AgentResponse:
    """Executes persona-driven financial screening or question answering."""
    mcp_client: MCPClient | None = getattr(request.app.state, "mcp_client", None)
    if mcp_client is None or mcp_client.session is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MCP tool server is not connected. Please verify MCP server subprocess.",
        )

    try:
        agent = FinancialAgent(
            persona=req.persona,
            sector=req.sector,
            mcp_client=mcp_client,
        )
        return await agent.query(req.query)
    except ValueError as val_err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(val_err),
        ) from val_err
    except Exception as exc:
        logger.error("Agent query failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Agent analysis failed: {str(exc)}",
        ) from exc


@app.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Operational Health Check",
    description="Returns service health status and MCP tool server connectivity.",
)
async def health_check(request: Request) -> HealthResponse:
    """Returns server and MCP client status."""
    mcp_client: MCPClient | None = getattr(request.app.state, "mcp_client", None)
    is_connected = mcp_client is not None and mcp_client.session is not None
    tools_count = len(mcp_client._tools_cache) if mcp_client else 0

    return HealthResponse(
        status="healthy" if is_connected else "degraded",
        version="1.0.0",
        mcp_server_connected=is_connected,
        tools_available=tools_count,
    )


@app.get(
    "/config",
    response_model=ConfigResponse,
    status_code=status.HTTP_200_OK,
    summary="Metadata Discovery",
    description="Returns lists of valid personas and sectors with full descriptions.",
)
async def get_config() -> ConfigResponse:
    """Discovers supported personas and sectors with descriptions."""
    personas = [
        ConfigOption(id=k, name=v["name"], description=v["description"])
        for k, v in PERSONA_METADATA.items()
    ]
    sectors = [
        ConfigOption(id=k, name=v["name"], description=v["description"])
        for k, v in SECTOR_METADATA.items()
    ]
    return ConfigResponse(personas=personas, sectors=sectors)
