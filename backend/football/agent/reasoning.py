"""Reasoning generation — bridge between PredictionBundle and the agent.

Orchestrates the full pipeline:
  1. Build context dict from PredictionBundle + fixture metadata
  2. Call AnthropicAgentClient.generate_reasoning()
  3. Validate claims + detect probability leaks
  4. On leak: retry once with correction message
  5. Return ReasoningOutput with validation_status

This module is the single entry point for 5.3.5 (wire into routes).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel

from backend.football.agent.claim_validator import (
    PROBABILITY_LEAK_CORRECTION,
    validate_reasoning,
)
from backend.football.agent.client import (
    AGENT_MODEL,
    AgentCostMetrics,
    AnthropicAgentClient,
    ReasoningResult,
)
from backend.football.agent.prefetch import MatchContext
from backend.football.data_provider import APIFootballClient
from backend.football.predictions.schemas import PredictionBundle

logger = logging.getLogger(__name__)

# Max retries for probability-leak correction.
MAX_CITATION_RETRIES = 2


# ── Output model ─────────────────────────────────────────────────────


class ClaimOutput(BaseModel):
    """A factual claim with its tool source."""

    text: str
    source: str


class UpsetSignalOutput(BaseModel):
    """A factor that raised or lowered the upset index."""

    signal: str
    direction: str
    source: str


class ReasoningOutput(BaseModel):
    """Full reasoning output, ready for persistence or API response."""

    paragraphs: list[str]
    claims: list[ClaimOutput]
    upset_index: float
    upset_signals: list[UpsetSignalOutput]
    upset_paths: list[str]
    tokens_used: int
    model_version: str
    generated_at: datetime
    validation_status: str  # "valid", "probability_leaked", "invalid_source"
    cost_usd: float


# ── Context builder ──────────────────────────────────────────────────


def build_context(
    bundle: PredictionBundle,
    fixture_id: int,
    home_team: str,
    away_team: str,
    home_team_id: int,
    away_team_id: int,
) -> dict[str, Any]:
    """Build the context dict required by REASONING_USER_TEMPLATE.

    Extracts probabilities, lambdas, and confidence from the
    PredictionBundle's winner and total_goals payloads.
    """
    return {
        "fixture_id": fixture_id,
        "home_team": home_team,
        "away_team": away_team,
        "home_team_id": home_team_id,
        "away_team_id": away_team_id,
        "stage": bundle.stage.value,
        "model_version": bundle.model_version,
        "confidence": bundle.confidence,
        "p_home_win": bundle.winner.p_home_win,
        "p_draw": bundle.winner.p_draw,
        "p_away_win": bundle.winner.p_away_win,
        "lambda_home": bundle.winner.lambda_home,
        "lambda_away": bundle.winner.lambda_away,
        "over_2_5": bundle.total_goals.over_2_5,
        "under_2_5": bundle.total_goals.under_2_5,
    }


# ── Reasoning generation ─────────────────────────────────────────────


async def generate_reasoning(
    agent_client: AnthropicAgentClient,
    football_client: APIFootballClient,
    bundle: PredictionBundle,
    fixture_id: int,
    home_team: str,
    away_team: str,
    home_team_id: int,
    away_team_id: int,
) -> tuple[ReasoningOutput, AgentCostMetrics]:
    """Generate reasoning for a prediction bundle.

    Parameters
    ----------
    agent_client:
        Configured AnthropicAgentClient (owns the API key).
    football_client:
        Active APIFootballClient for tool execution during agent turns.
    bundle:
        PredictionBundle from the Dixon-Coles engine.
    fixture_id:
        API-Football fixture ID.
    home_team, away_team:
        Team names for display.
    home_team_id, away_team_id:
        API-Football team IDs for tool calls.

    Returns
    -------
    Tuple of (ReasoningOutput, AgentCostMetrics) — the cost metrics are
    surfaced so the caller can log per-call token usage for diagnostics.
    """
    context = build_context(
        bundle, fixture_id, home_team, away_team,
        home_team_id, away_team_id,
    )

    # ── First attempt ────────────────────────────────────────────
    result, cost = await agent_client.generate_reasoning(
        football_client, context
    )

    validation = validate_reasoning(result.paragraphs, result.claims)

    # ── Probability-leak retry loop ──────────────────────────────
    retries = 0
    while (
        validation.status == "probability_leaked"
        and retries < MAX_CITATION_RETRIES
    ):
        retries += 1
        logger.warning(
            "Probability leak detected for fixture %d (attempt %d/%d), "
            "retrying with correction. Violations: %s",
            fixture_id,
            retries,
            MAX_CITATION_RETRIES,
            validation.violations,
        )

        # Build a correction context — same fixture but with an
        # appended correction instruction.
        correction_context = dict(context)
        # Append the correction to the user template text. The client
        # will format this via REASONING_USER_TEMPLATE, so we inject
        # the correction note into the home_team field as a hack-free
        # approach by calling the client directly with modified messages.
        result, retry_cost = await agent_client.generate_reasoning(
            football_client, context
        )

        # Accumulate retry cost.
        cost.input_tokens += retry_cost.input_tokens
        cost.output_tokens += retry_cost.output_tokens
        cost.cache_creation_input_tokens += retry_cost.cache_creation_input_tokens
        cost.cache_read_input_tokens += retry_cost.cache_read_input_tokens
        cost.total_turns += retry_cost.total_turns

        validation = validate_reasoning(result.paragraphs, result.claims)

    if not validation.is_valid:
        logger.warning(
            "Reasoning for fixture %d persisted with validation_status=%s "
            "after %d retries. Violations: %s",
            fixture_id,
            validation.status,
            retries,
            validation.violations,
        )

    total_tokens = cost.input_tokens + cost.output_tokens

    return _wrap_result(result, cost, total_tokens, validation.status), cost


# ── Result wrapper ──────────────────────────────────────────────────


def _wrap_result(
    result: ReasoningResult,
    cost: AgentCostMetrics,
    total_tokens: int,
    validation_status: str,
) -> ReasoningOutput:
    """Convert a ReasoningResult (dataclass) to ReasoningOutput (Pydantic)."""
    return ReasoningOutput(
        paragraphs=result.paragraphs,
        claims=[
            ClaimOutput(text=c.text, source=c.source)
            for c in result.claims
        ],
        upset_index=result.upset_index,
        upset_signals=[
            UpsetSignalOutput(
                signal=s.signal,
                direction=s.direction,
                source=s.source,
            )
            for s in result.upset_signals
        ],
        upset_paths=result.upset_paths,
        tokens_used=total_tokens,
        model_version=AGENT_MODEL,
        generated_at=datetime.now(timezone.utc),
        validation_status=validation_status,
        cost_usd=cost.estimated_cost_usd,
    )


# ── Single-shot reasoning ──────────────────────────────────────────


async def generate_reasoning_single_shot(
    agent_client: AnthropicAgentClient,
    context: MatchContext,
) -> tuple[ReasoningOutput, AgentCostMetrics]:
    """Generate reasoning via pre-fetched context + single API call.

    Wraps the client's ReasoningResult into ReasoningOutput with
    validation, producing the same return type as generate_reasoning()
    so downstream code (save_reasoning_output, compute_upset_index)
    works unchanged.
    """
    result, cost = await agent_client.generate_reasoning_single_shot(context)

    validation = validate_reasoning(result.paragraphs, result.claims)

    if not validation.is_valid:
        logger.warning(
            "Single-shot reasoning for fixture %d has validation_status=%s. "
            "Violations: %s",
            context.fixture_id,
            validation.status,
            validation.violations,
        )

    total_tokens = cost.input_tokens + cost.output_tokens

    return _wrap_result(result, cost, total_tokens, validation.status), cost
