"""FinancialAgent: Core persona-configurable financial AI agent.

Coordinates persona prompt assembly, LLM execution over OpenRouter/DeepSeek,
and live MCP tool calls over stdio to synthesize structured institutional research.
"""

import json
import os
import re
from typing import Any, Optional

from openai import AsyncOpenAI

from agent.config import (
    DEFAULT_API_KEY,
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    validate_config,
)
from agent.mcp_client import MCPClient
from agent.personas import build_system_prompt
from agent.response import AgentResponse, DataSourceRecord, DEFAULT_DISCLAIMER


class FinancialAgent:
    """Configurable financial AI agent capable of switching personas and sectors."""

    def __init__(
        self,
        persona: str,
        sector: str,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        mcp_client: Optional[MCPClient] = None,
        llm_client: Optional[Any] = None,
        max_iterations: int = 8,
    ):
        """Initializes the FinancialAgent with a specific persona and sector.
        
        Args:
            persona: One of 'mf_analyst', 'equity_analyst', 'pe_analyst'.
            sector: One of 'tech', 'retail', 'logistics'.
            model: Model identifier (defaults to OpenRouter deepseek model).
            base_url: Base URL for OpenAI-compatible endpoint.
            api_key: API key for the LLM provider.
            mcp_client: Optional shared or pre-configured MCPClient instance.
            llm_client: Optional custom or mock LLM client.
            max_iterations: Maximum tool-call iterations per query.
        """
        self.persona, self.sector = validate_config(persona, sector)
        self.model = model or DEFAULT_MODEL
        self.base_url = base_url or DEFAULT_BASE_URL
        self.api_key = api_key or DEFAULT_API_KEY or "dummy-key-for-mock"
        self.max_iterations = max_iterations

        self.system_prompt = build_system_prompt(self.persona, self.sector)

        # Initialize LLM client with explicit base_url and api_key
        if llm_client is not None:
            self.llm = llm_client
        else:
            self.llm = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
            )

        self.mcp = mcp_client or MCPClient()
        self._owns_mcp = mcp_client is None
        self.conversation_history: list[dict[str, Any]] = []

        # Native instrumentation for validation and audit observability
        self.api_call_count: int = 0
        self.token_usage: dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        self.last_tool_sequence: list[dict[str, Any]] = []

    def reset_history(self) -> None:
        """Clears multi-turn conversation history."""
        self.conversation_history = []

    async def close(self) -> None:
        """Shuts down the MCP client if owned by this agent."""
        if self._owns_mcp and self.mcp:
            await self.mcp.stop()

    async def __aenter__(self) -> "FinancialAgent":
        if self._owns_mcp:
            await self.mcp.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    async def query(self, user_message: str) -> AgentResponse:
        """Executes a complete financial analysis query against the MCP database.
        
        Args:
            user_message: Human query or API request text.
            
        Returns:
            AgentResponse: Structured JSON response with narrative and provenance.
        """
        if not self.mcp.session:
            await self.mcp.start()

        # Reset per-query instrumentation
        self.api_call_count = 0
        self.token_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        self.last_tool_sequence = []

        # Retrieve tool schemas translated to OpenAI function definitions
        tools = await self.mcp.get_tools_for_llm()

        # Construct message stream
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt}
        ]

        # Append existing conversation history for multi-turn sessions
        for turn in self.conversation_history:
            messages.append(turn)

        messages.append({"role": "user", "content": user_message})

        tools_used: list[str] = []
        raw_sources: list[dict[str, str]] = []
        queried_tickers: set[str] = set()
        out_of_scope_lookup: bool = False

        final_answer = ""
        iterations = 0

        while iterations < self.max_iterations:
            iterations += 1
            self.api_call_count += 1

            # Invoke LLM
            response = await self.llm.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools if tools else None,
                tool_choice="auto" if tools else None,
                temperature=0.2,
            )

            # Accumulate token usage if reported
            if hasattr(response, "usage") and response.usage:
                self.token_usage["prompt_tokens"] += getattr(response.usage, "prompt_tokens", 0) or 0
                self.token_usage["completion_tokens"] += getattr(response.usage, "completion_tokens", 0) or 0
                self.token_usage["total_tokens"] += getattr(response.usage, "total_tokens", 0) or 0

            choice = response.choices[0]
            msg = choice.message

            # Check if LLM generated tool calls
            if msg.tool_calls:
                # Add assistant message with tool calls to context
                messages.append(msg.model_dump() if hasattr(msg, "model_dump") else msg)

                for tool_call in msg.tool_calls:
                    fn_name = tool_call.function.name
                    try:
                        fn_args = json.loads(tool_call.function.arguments or "{}")
                    except Exception:
                        fn_args = {}

                    tools_used.append(fn_name)
                    self.last_tool_sequence.append({
                        "iteration": iterations,
                        "tool": fn_name,
                        "arguments": fn_args,
                    })

                    # Execute live MCP tool call over stdio
                    tool_result = await self.mcp.call_tool(fn_name, fn_args)

                    # Check for out-of-scope lookups
                    if isinstance(tool_result, dict) and "error" in tool_result and "not found" in str(tool_result["error"]).lower():
                        out_of_scope_lookup = True

                    # Extract verified tickers and provenance from the database output
                    extracted_sources, extracted_tickers = MCPClient.extract_provenance(
                        fn_name, fn_args, tool_result
                    )
                    raw_sources.extend(extracted_sources)
                    queried_tickers.update(extracted_tickers)

                    # Append tool result to messages
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(tool_result),
                    })
            else:
                # Final synthesized response
                final_answer = msg.content or ""
                break

        # Fallback if loop exceeded max iterations without returning final text
        if not final_answer:
            final_answer = "Analysis could not be completed within the execution limit."

        # Save turn to conversation history
        self.conversation_history.append({"role": "user", "content": user_message})
        self.conversation_history.append({"role": "assistant", "content": final_answer})

        # Process and deduplicate data sources directly from MCP tool provenance
        data_sources: list[DataSourceRecord] = []
        seen_sources: set[tuple[str, str, str]] = set()
        for src in raw_sources:
            key = (src.get("company", ""), src.get("metric_or_event", ""), src.get("source", ""))
            if key not in seen_sources:
                seen_sources.add(key)
                data_sources.append(DataSourceRecord(
                    company=src.get("company", ""),
                    metric_or_event=src.get("metric_or_event", ""),
                    source=src.get("source", ""),
                    source_url=src.get("source_url", ""),
                ))

        # Assess confidence score based on actual evidence availability
        ans_lower = final_answer.lower()
        is_refusal_or_oos = out_of_scope_lookup or any(
            phrase in ans_lower
            for phrase in [
                "not found in our coverage",
                "not found in my coverage",
                "no data on",
                "not have data",
                "don't have coverage",
                "do not have coverage",
                "not in my coverage",
                "not in our coverage",
                "coverage universe is limited",
                "does not appear in my available",
                "does not appear in our available",
                "company not found",
            ]
        )

        # Identify companies referenced:
        # Cross-reference tickers queried/retrieved from MCP tools with the final answer and query
        companies_referenced: list[str] = []
        if not (is_refusal_or_oos and len(data_sources) == 0):
            answer_upper = f"{user_message} {final_answer}".upper()
            for t in sorted(queried_tickers):
                # Verify ticker appears as a word in the text or was specifically queried
                if re.search(rf"\b{re.escape(t)}\b", answer_upper) or len(queried_tickers) <= 5:
                    companies_referenced.append(t)

        if len(data_sources) == 0:
            confidence = "medium" if is_refusal_or_oos else "low"
        elif is_refusal_or_oos or len(data_sources) < 3:
            confidence = "medium"
        else:
            confidence = "high"

        # Unique tool names preserving order
        unique_tools = list(dict.fromkeys(tools_used))

        return AgentResponse(
            answer=final_answer.strip(),
            persona=self.persona,
            sector=self.sector,
            companies_referenced=companies_referenced,
            tools_used=unique_tools,
            data_sources=data_sources,
            confidence=confidence,
            disclaimer=DEFAULT_DISCLAIMER,
        )
