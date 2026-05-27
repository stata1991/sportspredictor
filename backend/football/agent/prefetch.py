"""Pre-fetch match context for single-shot reasoning.

Replaces the agent tool loop by gathering all data upfront via
asyncio.gather(), then packaging it as a MatchContext dataclass
for inline inclusion in the Anthropic user message.

Each field is a pre-formatted text block matching the output format
of the corresponding tool implementation in tools.py, so the LLM
receives identical data to what the agent previously saw via
tool_result blocks.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from backend.football.agent.tools import (
    _exec_get_head_to_head,
    _exec_get_injuries,
    _exec_get_market_consensus,
    _exec_get_team_form,
)
from backend.football.data_provider import APIFootballClient
from backend.football.predictions.schemas import PredictionBundle

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MatchContext:
    """All external data needed for reasoning, pre-fetched in parallel.

    Each text field (home_form, away_form, head_to_head, injuries,
    market_consensus) contains the same plain-text output the tool
    implementations produce, so the LLM prompt is format-identical
    to the agent-loop era.
    """

    # Pre-fetched data (plain-text tool output)
    home_form: str
    away_form: str
    head_to_head: str
    injuries: str
    market_consensus: str

    # Prediction context (passed through from routes.py)
    fixture_id: int
    home_team: str
    away_team: str
    home_team_id: int
    away_team_id: int
    stage: str
    model_version: str
    confidence: str
    p_home_win: float
    p_draw: float
    p_away_win: float
    lambda_home: float
    lambda_away: float
    over_2_5: float
    under_2_5: float


def _resolve(result: str | BaseException, fallback: str) -> str:
    """Return the result if successful, or the fallback string on failure."""
    if isinstance(result, BaseException):
        logger.warning("Pre-fetch failed: %s", result)
        return fallback
    return result


async def pre_fetch_match_context(
    client: APIFootballClient,
    fixture_id: int,
    home_team: str,
    away_team: str,
    home_team_id: int,
    away_team_id: int,
    bundle: PredictionBundle,
) -> MatchContext:
    """Fetch all external data for reasoning in parallel.

    Calls all 4 API-Football data sources concurrently via
    asyncio.gather().  Each call reuses the existing tool
    implementation functions for output format consistency.

    Degrades gracefully: if a source fails, its field gets a
    fallback string and the LLM reasons without that data —
    identical to how the agent handled empty tool results.
    """
    results = await asyncio.gather(
        _exec_get_team_form(client, {
            "team_id": home_team_id,
            "team_name": home_team,
            "last": 5,
        }),
        _exec_get_team_form(client, {
            "team_id": away_team_id,
            "team_name": away_team,
            "last": 5,
        }),
        _exec_get_head_to_head(client, {
            "home_team_id": home_team_id,
            "away_team_id": away_team_id,
            "last": 10,
        }),
        _exec_get_injuries(client, {}),
        _exec_get_market_consensus(client, {
            "fixture_id": fixture_id,
        }),
        return_exceptions=True,
    )

    return MatchContext(
        home_form=_resolve(
            results[0],
            f"No recent form data available for {home_team}.",
        ),
        away_form=_resolve(
            results[1],
            f"No recent form data available for {away_team}.",
        ),
        head_to_head=_resolve(
            results[2],
            "No head-to-head data available.",
        ),
        injuries=_resolve(
            results[3],
            "Injury data unavailable.",
        ),
        market_consensus=_resolve(
            results[4],
            f"No odds available for fixture {fixture_id}.",
        ),
        fixture_id=fixture_id,
        home_team=home_team,
        away_team=away_team,
        home_team_id=home_team_id,
        away_team_id=away_team_id,
        stage=bundle.stage.value,
        model_version=bundle.model_version,
        confidence=bundle.confidence,
        p_home_win=bundle.winner.p_home_win,
        p_draw=bundle.winner.p_draw,
        p_away_win=bundle.winner.p_away_win,
        lambda_home=bundle.winner.lambda_home,
        lambda_away=bundle.winner.lambda_away,
        over_2_5=bundle.total_goals.over_2_5,
        under_2_5=bundle.total_goals.under_2_5,
    )
