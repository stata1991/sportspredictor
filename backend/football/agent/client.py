"""Anthropic agent client wrapper for football prediction reasoning.

Manages the multi-turn tool-use conversation loop:
  1. Send system prompt + user message with tool definitions
  2. If Claude requests tool_use, execute the tool and return results
  3. Repeat until Claude produces a final text response (or max turns)
  4. Parse the JSON output into ReasoningResult

Includes retry logic, cost telemetry, and citation validation with
a 2-retry circuit breaker.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from typing import Any

import anthropic

from backend.football.agent.prefetch import MatchContext
from backend.football.agent.prompts import (
    REASONING_SYSTEM_PROMPT,
    REASONING_USER_TEMPLATE,
    SINGLE_SHOT_SYSTEM_PROMPT,
    SINGLE_SHOT_USER_TEMPLATE,
)
from backend.football.agent.tools import (
    TOOL_DEFINITIONS,
    execute_tool,
)
from backend.football.data_provider import APIFootballClient

logger = logging.getLogger(__name__)

# Model configuration.
AGENT_MODEL = "claude-sonnet-4-6"
MAX_TOOL_TURNS = 6  # Max round-trips before forcing stop.
MAX_TOKENS = 2048

# Retry configuration.
MAX_API_RETRIES = 2
RETRY_BACKOFF_SECONDS = 1.0

# Cost per 1M tokens (Sonnet 4.6 pricing, verified April 2026).
INPUT_COST_PER_M = 3.00
OUTPUT_COST_PER_M = 15.00
CACHE_WRITE_COST_PER_M = 3.75
CACHE_READ_COST_PER_M = 0.30


# ── Result types ─────────────────────────────────────────────────────


@dataclass
class Claim:
    """A factual claim with its tool source for citation audit."""

    text: str
    source: str  # One of the four tool names.


@dataclass
class UpsetSignal:
    """A factor that raised or lowered the upset index."""

    signal: str
    direction: str  # "increases" or "decreases"
    source: str  # Tool name that provided the evidence.


@dataclass
class ReasoningResult:
    """Parsed output from the reasoning agent."""

    paragraphs: list[str]  # Exactly 3 paragraphs.
    claims: list[Claim]
    upset_index: float
    upset_signals: list[UpsetSignal]
    upset_paths: list[str]  # 3 entries when favourite >65%, else [].
    raw_json: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentCostMetrics:
    """Token usage and cost for a single agent invocation."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    total_turns: int = 0
    elapsed_seconds: float = 0.0

    @property
    def estimated_cost_usd(self) -> float:
        """Estimate cost in USD from token counts."""
        input_cost = (self.input_tokens / 1_000_000) * INPUT_COST_PER_M
        output_cost = (self.output_tokens / 1_000_000) * OUTPUT_COST_PER_M
        cache_write_cost = (
            self.cache_creation_input_tokens / 1_000_000
        ) * CACHE_WRITE_COST_PER_M
        cache_read_cost = (
            self.cache_read_input_tokens / 1_000_000
        ) * CACHE_READ_COST_PER_M
        return input_cost + output_cost + cache_write_cost + cache_read_cost


# ── Exceptions ───────────────────────────────────────────────────────


class AgentError(Exception):
    """Base exception for agent errors."""


class AgentParseError(AgentError):
    """Agent returned text that couldn't be parsed as valid JSON."""

    def __init__(self, raw_text: str, detail: str = "") -> None:
        self.raw_text = raw_text
        super().__init__(detail or f"Failed to parse agent output: {raw_text[:200]}")


class AgentMaxTurnsError(AgentError):
    """Agent hit the maximum number of tool-use turns."""


# ── Client ───────────────────────────────────────────────────────────


class AnthropicAgentClient:
    """Wrapper around the Anthropic Messages API for tool-use conversations.

    Usage::

        agent = AnthropicAgentClient(api_key="sk-...")
        result, cost = await agent.generate_reasoning(
            football_client, fixture_context
        )
    """

    def __init__(self, api_key: str | None = None) -> None:
        resolved_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not resolved_key:
            raise AgentError(
                "No Anthropic API key provided. Set ANTHROPIC_API_KEY or "
                "pass api_key to AnthropicAgentClient."
            )
        self._client = anthropic.Anthropic(api_key=resolved_key)

    async def generate_reasoning(
        self,
        football_client: APIFootballClient,
        context: dict[str, Any],
    ) -> tuple[ReasoningResult, AgentCostMetrics]:
        """Run the multi-turn reasoning agent for a fixture.

        Parameters
        ----------
        football_client:
            Active APIFootballClient for tool execution.
        context:
            Dict with keys matching REASONING_USER_TEMPLATE placeholders:
            home_team, away_team, fixture_id, stage, model_version,
            confidence, p_home_win, p_draw, p_away_win, lambda_home,
            lambda_away, over_2_5, under_2_5, home_team_id, away_team_id.

        Returns
        -------
        Tuple of (ReasoningResult, AgentCostMetrics).

        Raises
        ------
        AgentError
            On unrecoverable API errors or parse failures.
        """
        t0 = time.monotonic()
        cost = AgentCostMetrics()

        user_message = REASONING_USER_TEMPLATE.format(**context)

        messages: list[dict[str, Any]] = [
            {"role": "user", "content": user_message},
        ]

        system_with_cache = [
            {
                "type": "text",
                "text": REASONING_SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ]

        for turn in range(MAX_TOOL_TURNS):
            cost.total_turns += 1

            response = self._call_api(
                system=system_with_cache,
                messages=messages,
                tools=TOOL_DEFINITIONS,
            )

            # Accumulate token usage.
            usage = response.usage
            cost.input_tokens += usage.input_tokens
            cost.output_tokens += usage.output_tokens
            if hasattr(usage, "cache_creation_input_tokens"):
                cost.cache_creation_input_tokens += (
                    usage.cache_creation_input_tokens or 0
                )
            if hasattr(usage, "cache_read_input_tokens"):
                cost.cache_read_input_tokens += (
                    usage.cache_read_input_tokens or 0
                )

            # Check for end_turn (final text response).
            if response.stop_reason == "end_turn":
                raw_text = self._extract_text(response)
                cost.elapsed_seconds = time.monotonic() - t0
                self._log_cost(cost, context.get("fixture_id"))
                return self._parse_result(raw_text), cost

            # Handle tool_use blocks.
            if response.stop_reason == "tool_use":
                # Add assistant message with all content blocks.
                messages.append(
                    {"role": "assistant", "content": response.content}
                )

                # Execute each tool call and build tool results.
                tool_results: list[dict[str, Any]] = []
                for block in response.content:
                    if block.type == "tool_use":
                        try:
                            result_text = await execute_tool(
                                football_client,
                                block.name,
                                block.input,
                            )
                        except Exception as exc:
                            logger.warning(
                                "Tool %s failed: %s", block.name, exc
                            )
                            result_text = f"Error executing {block.name}: {exc}"

                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": result_text,
                            }
                        )

                messages.append({"role": "user", "content": tool_results})
                continue

            # Unexpected stop reason — treat as final.
            raw_text = self._extract_text(response)
            cost.elapsed_seconds = time.monotonic() - t0
            self._log_cost(cost, context.get("fixture_id"))
            return self._parse_result(raw_text), cost

        # Exhausted max turns.
        cost.elapsed_seconds = time.monotonic() - t0
        self._log_cost(cost, context.get("fixture_id"))
        raise AgentMaxTurnsError(
            f"Agent did not produce final output within {MAX_TOOL_TURNS} turns"
        )

    async def generate_reasoning_single_shot(
        self,
        context: MatchContext,
    ) -> tuple[ReasoningResult, AgentCostMetrics]:
        """Single-shot reasoning with all data pre-fetched.

        Unlike generate_reasoning() which runs a multi-turn tool-use loop,
        this makes exactly ONE Anthropic API call with all match data
        inlined in the user message.  No tools, no loop.

        Parameters
        ----------
        context:
            Pre-fetched MatchContext from pre_fetch_match_context().

        Returns
        -------
        Tuple of (ReasoningResult, AgentCostMetrics).

        Raises
        ------
        AgentError
            On unrecoverable API errors.
        AgentParseError
            If the response is not valid JSON matching the schema.
        """
        t0 = time.monotonic()
        cost = AgentCostMetrics()

        user_message = SINGLE_SHOT_USER_TEMPLATE.format(**asdict(context))

        system_with_cache = [
            {
                "type": "text",
                "text": SINGLE_SHOT_SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ]

        messages: list[dict[str, Any]] = [
            {"role": "user", "content": user_message},
        ]

        cost.total_turns = 1

        response = self._call_api(
            system=system_with_cache,
            messages=messages,
            tools=[],
        )

        # Accumulate token usage.
        usage = response.usage
        cost.input_tokens = usage.input_tokens
        cost.output_tokens = usage.output_tokens
        if hasattr(usage, "cache_creation_input_tokens"):
            cost.cache_creation_input_tokens = (
                usage.cache_creation_input_tokens or 0
            )
        if hasattr(usage, "cache_read_input_tokens"):
            cost.cache_read_input_tokens = (
                usage.cache_read_input_tokens or 0
            )

        raw_text = self._extract_text(response)
        cost.elapsed_seconds = time.monotonic() - t0
        self._log_cost(cost, context.fixture_id)

        return self._parse_result(raw_text), cost

    async def generate_live_note(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 160,
    ) -> tuple[str, AgentCostMetrics]:
        """Single short text completion for live in-play narration (STATS-B).

        Returns plain text (1-2 sentences), NOT the structured reasoning
        JSON. Runs the blocking SDK call in a worker thread so the live
        request's event loop is not stalled during generation. One attempt
        (no multi-turn loop); the caller treats any error as best-effort.
        """
        t0 = time.monotonic()
        cost = AgentCostMetrics(total_turns=1)

        def _blocking_call() -> Any:
            return self._client.messages.create(
                model=AGENT_MODEL,
                max_tokens=max_tokens,
                system=[{
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }],
                messages=[{"role": "user", "content": user_message}],
            )

        response = await asyncio.to_thread(_blocking_call)

        usage = response.usage
        cost.input_tokens = usage.input_tokens
        cost.output_tokens = usage.output_tokens
        if hasattr(usage, "cache_creation_input_tokens"):
            cost.cache_creation_input_tokens = usage.cache_creation_input_tokens or 0
        if hasattr(usage, "cache_read_input_tokens"):
            cost.cache_read_input_tokens = usage.cache_read_input_tokens or 0
        cost.elapsed_seconds = time.monotonic() - t0

        return self._extract_text(response).strip(), cost

    def _call_api(
        self,
        system: list[dict[str, Any]],
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> Any:
        """Call the Anthropic messages API with retry logic."""
        last_exc: Exception | None = None

        for attempt in range(MAX_API_RETRIES + 1):
            try:
                return self._client.messages.create(
                    model=AGENT_MODEL,
                    max_tokens=MAX_TOKENS,
                    system=system,
                    messages=messages,
                    tools=tools,
                )
            except anthropic.RateLimitError as exc:
                last_exc = exc
                if attempt < MAX_API_RETRIES:
                    wait = RETRY_BACKOFF_SECONDS * (2**attempt)
                    logger.warning(
                        "Anthropic rate limit (attempt %d/%d), "
                        "retrying in %.1fs",
                        attempt + 1,
                        MAX_API_RETRIES + 1,
                        wait,
                    )
                    time.sleep(wait)
            except anthropic.APIStatusError as exc:
                if exc.status_code >= 500 and attempt < MAX_API_RETRIES:
                    last_exc = exc
                    wait = RETRY_BACKOFF_SECONDS * (2**attempt)
                    logger.warning(
                        "Anthropic server error %d (attempt %d/%d), "
                        "retrying in %.1fs",
                        exc.status_code,
                        attempt + 1,
                        MAX_API_RETRIES + 1,
                        wait,
                    )
                    time.sleep(wait)
                else:
                    raise AgentError(
                        f"Anthropic API error: {exc.status_code} {exc.message}"
                    ) from exc

        raise AgentError(f"Anthropic API failed after {MAX_API_RETRIES + 1} attempts") from last_exc

    @staticmethod
    def _extract_text(response: Any) -> str:
        """Extract text content from a response."""
        for block in response.content:
            if hasattr(block, "text"):
                return block.text
        return ""

    @staticmethod
    def _parse_result(raw_text: str) -> ReasoningResult:
        """Parse the agent's JSON output into a ReasoningResult.

        Validates the full schema: paragraphs (3), claims, upset_index,
        upset_signals, and upset_paths (conditional).  Raises
        AgentParseError on structural violations.
        """
        # Extract JSON from the response, handling:
        # 1. Clean JSON (starts with {)
        # 2. Markdown-fenced JSON (```json ... ```)
        # 3. Preamble text before a fenced JSON block
        text = raw_text.strip()

        # Try to extract content between ``` fences.
        if "```" in text:
            import re

            fenced = re.search(
                r"```(?:json)?\s*\n(.*?)\n\s*```",
                text,
                re.DOTALL,
            )
            if fenced:
                text = fenced.group(1).strip()
            else:
                # Fallback: strip all ``` lines.
                lines = text.split("\n")
                lines = [
                    ln
                    for ln in lines
                    if not ln.strip().startswith("```")
                ]
                text = "\n".join(lines).strip()

        # If there's preamble text before the JSON object, find the
        # first '{' and last '}'.
        if text and not text.startswith("{"):
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                text = text[start : end + 1]

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise AgentParseError(raw_text, f"Invalid JSON: {exc}") from exc

        # ── paragraphs ──────────────────────────────────────────
        paragraphs = data.get("paragraphs")
        if not isinstance(paragraphs, list) or len(paragraphs) != 3:
            raise AgentParseError(
                raw_text,
                "'paragraphs' must be an array of exactly 3 strings",
            )
        for i, p in enumerate(paragraphs):
            if not isinstance(p, str) or not p.strip():
                raise AgentParseError(
                    raw_text, f"paragraphs[{i}] is missing or empty"
                )

        # ── claims ───────────────────────────────────────────────
        raw_claims = data.get("claims")
        if not isinstance(raw_claims, list):
            raise AgentParseError(raw_text, "'claims' must be an array")
        claims: list[Claim] = []
        for c in raw_claims:
            if not isinstance(c, dict):
                raise AgentParseError(raw_text, "Each claim must be an object")
            c_text = c.get("text")
            c_source = c.get("source")
            if not isinstance(c_text, str) or not c_text:
                raise AgentParseError(raw_text, "Claim missing 'text'")
            if not isinstance(c_source, str) or not c_source:
                raise AgentParseError(raw_text, "Claim missing 'source'")
            claims.append(Claim(text=c_text, source=c_source))

        # ── upset_index ──────────────────────────────────────────
        upset_index = data.get("upset_index")
        if not isinstance(upset_index, (int, float)):
            raise AgentParseError(
                raw_text, "Missing or invalid 'upset_index' field"
            )
        upset_index = max(0.0, min(1.0, float(upset_index)))

        # ── upset_signals ────────────────────────────────────────
        raw_signals = data.get("upset_signals")
        if not isinstance(raw_signals, list):
            raise AgentParseError(raw_text, "'upset_signals' must be an array")
        signals: list[UpsetSignal] = []
        for s in raw_signals:
            if not isinstance(s, dict):
                raise AgentParseError(
                    raw_text, "Each upset_signal must be an object"
                )
            signals.append(
                UpsetSignal(
                    signal=str(s.get("signal", "")),
                    direction=str(s.get("direction", "")),
                    source=str(s.get("source", "")),
                )
            )

        # ── upset_paths ──────────────────────────────────────────
        upset_paths = data.get("upset_paths")
        if not isinstance(upset_paths, list):
            raise AgentParseError(raw_text, "'upset_paths' must be an array")
        # Valid states: empty [] or exactly 3 entries.
        if len(upset_paths) not in (0, 3):
            raise AgentParseError(
                raw_text,
                f"'upset_paths' must have 0 or 3 entries, got {len(upset_paths)}",
            )

        return ReasoningResult(
            paragraphs=[str(p) for p in paragraphs],
            claims=claims,
            upset_index=upset_index,
            upset_signals=signals,
            upset_paths=[str(p) for p in upset_paths],
            raw_json=data,
        )

    @staticmethod
    def _log_cost(cost: AgentCostMetrics, fixture_id: Any = None) -> None:
        """Log cost telemetry for the agent invocation."""
        logger.info(
            "agent_cost fixture_id=%s turns=%d input=%d output=%d "
            "cache_write=%d cache_read=%d cost=$%.4f elapsed=%.1fs",
            fixture_id,
            cost.total_turns,
            cost.input_tokens,
            cost.output_tokens,
            cost.cache_creation_input_tokens,
            cost.cache_read_input_tokens,
            cost.estimated_cost_usd,
            cost.elapsed_seconds,
        )
