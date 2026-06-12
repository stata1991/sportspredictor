"""Football API routes.

Mounted at ``/api/football`` by main.py.
"""

from __future__ import annotations

import json
import logging
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, NoReturn

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.football._perf import _emit, timed_step
from backend.football.agent.client import AnthropicAgentClient
from backend.football.agent.prefetch import pre_fetch_match_context
from backend.football.agent.reasoning import (
    ReasoningOutput,
    generate_reasoning,
    generate_reasoning_single_shot,
)
from backend.football.agent.upset import UpsetOutput, compute_upset_index
from backend.football.constants import BASE_URL, WC_LEAGUE_ID, WC_SEASON
from backend.football.data_provider import APIFootballClient
from backend.football.deps import get_agent_client, get_football_client
from backend.football.exceptions import (
    APIFootballError,
    PlanLimitationError,
    QuotaExhaustedError,
    RateLimitError,
    UpstreamError,
)
from backend.football.evaluation.receipts import build_match_receipt
from backend.football.persistence import (
    get_all_accuracy_rollups,
    get_cached_bundle,
    get_evaluated_match_rows,
    get_cached_live_prediction,
    get_cached_reasoning,
    get_latest_predictions_for_fixture,
    get_latest_reasoning,
    get_predictions_for_fixture,
    get_upsets_above_threshold,
    save_live_prediction,
    save_prediction_bundle,
    save_reasoning_output,
    save_upset_output,
)
from backend.football.predictions.derivations import derive_live_v1, is_unknown_round
from backend.football.predictions.engine import (
    PredictionEngine,
    detect_stage,
)
from backend.football.predictions.schemas import FixtureStage
from backend.football.schemas import CoverageStatus
from backend.shared.db import AsyncSessionLocal, get_session
from backend.shared.settings import get_settings

logger = logging.getLogger(__name__)

router = APIRouter()


# ── CDN Cache-Control TTLs (seconds) ────────────────────────────────
# These drive CloudFront / browser caching via Cache-Control headers.

_CC_FIXTURES_LIST = 300      # 5 min  — schedule changes infrequently
_CC_FIXTURES_LIVE = 15       # 15 s   — fixtures list while a match is live
_CC_FIXTURE_NS = 300         # 5 min  — not started, low volatility
_CC_FIXTURE_LIVE = 30        # 30 s   — in-play, high volatility
_CC_FIXTURE_COMPLETED = 86400  # 24 h — result is final
_CC_COVERAGE = 3600          # 1 h    — coverage flags rarely change
_CC_STANDINGS = 60           # 60 s   — standings update after matches
_CC_UPSETS = 120             # 2 min  — new upsets can appear
_CC_H2H = 3600              # 1 h    — historical record, rarely changes
_CC_PRE_MATCH_FRESH = 1800   # 30 min — freshly generated
_CC_PRE_MATCH_CACHED = 300   # 5 min  — already cached, shorter refresh
_CC_LIVE_PRED = 30           # 30 s   — real-time
_CC_REASONING = 300          # 5 min  — stable once generated
_CC_HISTORY = 120            # 2 min  — append-only, moderate
_CC_ACCURACY = 300           # 5 min  — computed periodically


# In-play fixture statuses (mirrors engine._LIVE) for live-aware caching.
_LIVE_STATUSES = frozenset({"1H", "2H", "HT", "ET", "BT", "P", "LIVE"})


def _set_cache(response: Response, max_age: int) -> None:
    """Set Cache-Control header for CDN and browser caching."""
    response.headers["Cache-Control"] = f"public, max-age={max_age}"


def _emit_unknown_round(round_str: str | None, fixture_id: int) -> bool:
    """Tripwire: emit a structured warning when a fixture's round string is
    neither a known knockout nor a known group-stage round.

    Converts a silent misclassification — API-Football naming a 2026 round
    something our constants didn't anticipate, which would make a knockout
    fixture fall through to ternary probabilities — into a greppable log line
    (``unknown_round_string``). Does NOT change classification. Returns True
    if a warning was emitted.
    """
    if not is_unknown_round(round_str):
        return False
    _emit({
        "event": "unknown_round_string",
        "round": round_str,
        "fixture_id": fixture_id,
    })
    return True

# ── Prediction engine singleton ──────────────────────────────────────

_engine: PredictionEngine | None = None


def _get_engine() -> PredictionEngine:
    """Lazily initialise the prediction engine singleton."""
    global _engine
    if _engine is None:
        _engine = PredictionEngine()
    return _engine


# ── Reasoning serialisation helpers ───────────────────────────────────


def _reasoning_to_dict(r: ReasoningOutput) -> dict[str, Any]:
    """Convert ReasoningOutput to a JSON-safe dict for the API response."""
    return {
        "paragraphs": r.paragraphs,
        "claims": [{"text": c.text, "source": c.source} for c in r.claims],
        "upset_index": r.upset_index,
        "upset_signals": [
            {"signal": s.signal, "direction": s.direction, "source": s.source}
            for s in r.upset_signals
        ],
        "upset_paths": r.upset_paths,
        "validation_status": r.validation_status,
    }


def _upset_to_dict(u: UpsetOutput) -> dict[str, Any]:
    """Convert UpsetOutput to a JSON-safe dict for the API response."""
    return {
        "upset_index": u.upset_index,
        "deterministic_component": u.deterministic_component,
        "agent_component": u.agent_component,
        "bounded_agent": u.bounded_agent,
        "upset_signals": [
            {"signal": s.signal, "direction": s.direction, "source": s.source}
            for s in u.upset_signals
        ],
        "upset_paths": u.upset_paths,
    }


# ── Error translation ─────────────────────────────────────────────────


def _raise_for_football_error(exc: APIFootballError) -> NoReturn:
    """Convert a football exception into the appropriate HTTPException."""
    if isinstance(exc, (RateLimitError, QuotaExhaustedError)):
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    if isinstance(exc, PlanLimitationError):
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if isinstance(exc, UpstreamError):
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    # ParseError, generic APIFootballError
    raise HTTPException(status_code=502, detail=str(exc)) from exc


# ── Data endpoints ────────────────────────────────────────────────────


@router.get("/health")
async def health() -> dict:
    """Health check — no upstream call, no auth required."""
    return {
        "status": "ok",
        "provider": "api-football",
        "base_url": BASE_URL,
    }


@router.get("/fixtures")
async def list_fixtures(
    response: Response,
    league: int = WC_LEAGUE_ID,
    season: int = WC_SEASON,
    live: bool = Query(False),
    client: APIFootballClient = Depends(get_football_client),
) -> dict:
    """List all fixtures for a league/season.

    ``live=1`` (sent by the frontend only while a match is in play and the
    tab is visible) shortens both the upstream cache TTL and the
    ``Cache-Control`` so in-play score/minute stay fresh. Score/status only —
    this endpoint carries no prediction values.
    """
    try:
        fixtures = await client.get_fixtures(
            league=league, season=season, live=live,
        )
    except APIFootballError as exc:
        _raise_for_football_error(exc)

    # Short Cache-Control whenever the request is a live poll OR the response
    # actually contains an in-play fixture (so a normal load during a match
    # isn't frozen by the browser/CDN for 5 minutes).
    live_present = any(
        fx.fixture.status.short in _LIVE_STATUSES for fx in fixtures
    )
    _set_cache(
        response,
        _CC_FIXTURES_LIVE if (live or live_present) else _CC_FIXTURES_LIST,
    )
    return {
        "count": len(fixtures),
        "fixtures": [fx.model_dump(mode="json") for fx in fixtures],
    }


@router.get("/fixtures/rounds")
async def list_rounds(
    response: Response,
    league: int = WC_LEAGUE_ID,
    season: int = WC_SEASON,
    client: APIFootballClient = Depends(get_football_client),
) -> dict:
    """Available rounds for a league/season."""
    try:
        rounds = await client.get_rounds(league=league, season=season)
    except APIFootballError as exc:
        _raise_for_football_error(exc)

    _set_cache(response, _CC_FIXTURES_LIST)
    return {
        "count": len(rounds),
        "rounds": rounds,
    }


@router.get("/fixtures/{fixture_id}")
async def get_fixture(
    fixture_id: int,
    response: Response,
    client: APIFootballClient = Depends(get_football_client),
) -> dict:
    """Single fixture by ID."""
    try:
        fixture = await client.get_fixture(fixture_id)
    except APIFootballError as exc:
        _raise_for_football_error(exc)

    if fixture is None:
        raise HTTPException(
            status_code=404, detail=f"Fixture {fixture_id} not found"
        )
    status = fixture.fixture.status.short
    if status in _FINISHED_STATUSES:
        _set_cache(response, _CC_FIXTURE_COMPLETED)
    elif status in ("1H", "2H", "HT", "ET", "BT", "P", "INT", "LIVE"):
        _set_cache(response, _CC_FIXTURE_LIVE)
    else:
        _set_cache(response, _CC_FIXTURE_NS)
    return fixture.model_dump(mode="json")


@router.get("/coverage")
async def get_coverage(
    response: Response,
    client: APIFootballClient = Depends(get_football_client),
) -> dict:
    """Coverage flags for WC 2026 with gap warnings."""
    try:
        cov = await client.get_coverage()
    except APIFootballError as exc:
        _raise_for_football_error(exc)

    if cov is None:
        raise HTTPException(
            status_code=404, detail="Coverage data not available"
        )
    _set_cache(response, _CC_COVERAGE)
    status = CoverageStatus.from_af_coverage(cov)
    return status.model_dump()


@router.get("/standings")
async def get_standings(
    response: Response,
    league: int = WC_LEAGUE_ID,
    season: int = WC_SEASON,
    client: APIFootballClient = Depends(get_football_client),
) -> dict:
    """Group standings for a league/season."""
    try:
        standings = await client.get_standings(league=league, season=season)
    except APIFootballError as exc:
        _raise_for_football_error(exc)

    if standings is None:
        _set_cache(response, _CC_STANDINGS)
        return {"league": None, "groups": []}

    _set_cache(response, _CC_STANDINGS)
    return standings.model_dump(mode="json", by_alias=True)


# ── Head-to-head endpoint ─────────────────────────────────────────────


@router.get("/head-to-head")
async def get_head_to_head(
    response: Response,
    team1: int = Query(..., description="API-Football team ID for team 1"),
    team2: int = Query(..., description="API-Football team ID for team 2"),
    last: int = Query(5, ge=1, le=10, description="Number of recent meetings"),
    client: APIFootballClient = Depends(get_football_client),
) -> dict:
    """Head-to-head history between two teams.

    Returns last N meetings with scores, dates, and a summary
    (wins/draws/losses from team1's perspective).
    """
    try:
        fixtures = await client.get_head_to_head(team1, team2, last=last)
    except APIFootballError as exc:
        _raise_for_football_error(exc)

    # Compute W-D-L from team1's perspective.
    wins, draws, losses = 0, 0, 0
    for fx in fixtures:
        if fx.goals.home is None or fx.goals.away is None:
            continue
        # Determine if team1 was home or away in this fixture.
        if fx.teams.home.id == team1:
            if fx.goals.home > fx.goals.away:
                wins += 1
            elif fx.goals.home < fx.goals.away:
                losses += 1
            else:
                draws += 1
        elif fx.teams.away.id == team1:
            if fx.goals.away > fx.goals.home:
                wins += 1
            elif fx.goals.away < fx.goals.home:
                losses += 1
            else:
                draws += 1
        else:
            draws += 1  # Shouldn't happen, but defensive.

    _set_cache(response, _CC_H2H)
    return {
        "team1_id": team1,
        "team2_id": team2,
        "count": len(fixtures),
        "summary": {"wins": wins, "draws": draws, "losses": losses},
        "fixtures": [fx.model_dump(mode="json") for fx in fixtures],
    }


# ── Upset watch endpoint ──────────────────────────────────────────────

# Statuses for finished/cancelled fixtures — excluded from upset watch.
_FINISHED_STATUSES = frozenset(
    {"FT", "AET", "PST", "CANC", "ABD", "AWD", "WO"}
)


@router.get("/upsets")
async def list_upsets(
    response: Response,
    threshold: float = Query(0.45, ge=0.0, le=1.0),
    client: APIFootballClient = Depends(get_football_client),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Upset watch list — fixtures with upset_index >= threshold.

    Read-only DB query + fixture metadata from API-Football.
    Never triggers prediction generation.  Returns only upcoming/live
    fixtures (excludes FT, AET, PST, CANC, etc.).

    Sorted by upset_index descending.
    """
    _set_cache(response, _CC_UPSETS)

    # 1. Query DB for qualifying predictions.
    predictions = await get_upsets_above_threshold(session, threshold)
    if not predictions:
        return {"count": 0, "threshold": threshold, "upsets": []}

    # 2. Fetch all fixtures for the league/season (cached by data provider).
    try:
        all_fixtures = await client.get_fixtures(
            league=WC_LEAGUE_ID, season=WC_SEASON
        )
    except APIFootballError as exc:
        _raise_for_football_error(exc)

    # 3. Build fixture lookup by ID.
    fixture_map = {fx.fixture.id: fx for fx in all_fixtures}

    # 4. Combine prediction data with fixture metadata, filtering out
    #    finished/cancelled fixtures.
    upsets: list[dict] = []
    for pred in predictions:
        fx = fixture_map.get(pred.fixture_id)
        if fx is None:
            logger.warning(
                "Fixture %d has upset prediction but not found in "
                "API-Football fixtures list",
                pred.fixture_id,
            )
            continue

        status = fx.fixture.status.short
        if status in _FINISHED_STATUSES:
            continue

        upsets.append(
            {
                "fixture_id": pred.fixture_id,
                "home_team": fx.teams.home.name,
                "away_team": fx.teams.away.name,
                "home_logo": fx.teams.home.logo,
                "away_logo": fx.teams.away.logo,
                "kickoff": fx.fixture.date.isoformat(),
                "status": status,
                "round": fx.league.round,
                "upset_index": float(pred.upset_index),
                "upset_paths": pred.payload.get("upset_paths", []),
            }
        )

    return {
        "count": len(upsets),
        "threshold": threshold,
        "upsets": upsets,
    }


# ── Prediction endpoints ─────────────────────────────────────────────


@router.get("/predict/pre-match/{fixture_id}")
async def predict_pre_match(
    fixture_id: int,
    response: Response,
    client: APIFootballClient = Depends(get_football_client),
    session: AsyncSession = Depends(get_session),
    agent_client: AnthropicAgentClient | None = Depends(get_agent_client),
) -> dict:
    """Generate (or return cached) pre-match predictions for a fixture.

    1-hour cache per stage: if a fresh prediction exists at the current
    stage, return it.  Otherwise generate, persist, and return.

    Reasoning generation (via Anthropic agent) runs after the
    deterministic prediction is committed.  Agent failures are
    caught and logged — the deterministic prediction is never
    blocked by reasoning failures.

    - CompletedFixtureError  -> 200 with historical predictions
    - NotPredictableError    -> 422
    - Live status            -> 422 (use /predict/live/ instead)
    """
    # ── Fetch fixture from API ──────────────────────────────────
    with timed_step("fetch_fixture", fixture_id=fixture_id):
        try:
            fx = await client.get_fixture(fixture_id)
        except APIFootballError as exc:
            _raise_for_football_error(exc)

        if fx is None:
            raise HTTPException(404, f"Fixture {fixture_id} not found")

        status = fx.fixture.status.short
        home_id = fx.teams.home.id
        away_id = fx.teams.away.id

        # ── Check lineups for NS/TBD fixtures ───────────────────
        has_lineups = False
        if status in ("NS", "TBD"):
            try:
                lineups = await client.get_lineups(fixture_id)
                has_lineups = len(lineups) > 0
            except APIFootballError:
                pass  # proceed without lineup info

    # ── Detect stage ────────────────────────────────────────────
    stage = detect_stage(status, has_lineups=has_lineups)

    # ── Completed → return historical predictions ───────────────
    if stage is FixtureStage.COMPLETED:
        latest = await get_latest_predictions_for_fixture(
            session, fixture_id
        )
        _set_cache(response, _CC_FIXTURE_COMPLETED)
        return {
            "fixture_id": fixture_id,
            "home_team": fx.teams.home.name,
            "away_team": fx.teams.away.name,
            "home_team_id": home_id,
            "away_team_id": away_id,
            "status": status,
            "stage": "completed",
            "round": fx.league.round,
            "cached": True,
            "message": (
                "Fixture already completed. Returning most recent "
                "pre-match predictions."
            ),
            "predictions": {k: v.payload for k, v in latest.items()},
        }

    # ── Not predictable → 422 ──────────────────────────────────
    if stage is FixtureStage.NOT_PREDICTABLE:
        raise HTTPException(
            422, f"Fixture status '{status}' is not predictable"
        )

    # ── Live → redirect to the live endpoint ────────────────────
    if stage is FixtureStage.LIVE:
        raise HTTPException(
            422,
            "Fixture is live. Use /predict/live/{fixture_id} instead.",
        )

    # ── Check DB cache (1-hour freshness at current stage) ──────
    cached = await get_cached_bundle(session, fixture_id, stage.value)
    if cached is not None:
        # Also check for cached reasoning.
        reasoning_payload = None
        upset_payload = None
        cached_r = await get_cached_reasoning(
            session, fixture_id, stage.value
        )
        if cached_r is not None:
            reasoning_payload = cached_r["reasoning"].payload
            upset_payload = cached_r["upset_index"].payload

        _set_cache(response, _CC_PRE_MATCH_CACHED)
        return {
            "fixture_id": fixture_id,
            "home_team": fx.teams.home.name,
            "away_team": fx.teams.away.name,
            "home_team_id": home_id,
            "away_team_id": away_id,
            "status": status,
            "stage": stage.value,
            "round": fx.league.round,
            "cached": True,
            "predictions": {k: v.payload for k, v in cached.items()},
            "reasoning": reasoning_payload,
            "upset": upset_payload,
        }

    # ── Generate fresh predictions ──────────────────────────────
    _emit_unknown_round(fx.league.round, fixture_id)
    with timed_step("dixon_coles", fixture_id=fixture_id):
        engine = _get_engine()
        bundle = engine.predict(
            home_id, away_id, status,
            has_lineups=has_lineups,
            round_str=fx.league.round,
        )

    # ── Persist deterministic predictions ─────────────────────
    # Commit BEFORE reasoning so agent failure can't roll back.
    await save_prediction_bundle(session, fixture_id, bundle)
    await session.commit()

    logger.info(
        "Generated pre-match predictions for fixture %d (stage=%s)",
        fixture_id,
        stage.value,
    )

    # ── Reasoning generation (failure-tolerant) ───────────────
    reasoning_payload = None
    upset_payload = None

    if agent_client is not None:
        # Check reasoning cache first.
        cached_r = await get_cached_reasoning(
            session, fixture_id, stage.value
        )
        if cached_r is not None:
            reasoning_payload = cached_r["reasoning"].payload
            upset_payload = cached_r["upset_index"].payload
        else:
            try:
                settings = get_settings()
                if settings.use_single_shot_reasoning:
                    with timed_step("pre_fetch_context", fixture_id=fixture_id):
                        ctx = await pre_fetch_match_context(
                            client=client,
                            fixture_id=fixture_id,
                            home_team=fx.teams.home.name,
                            away_team=fx.teams.away.name,
                            home_team_id=home_id,
                            away_team_id=away_id,
                            bundle=bundle,
                        )
                    with timed_step("anthropic_reasoning", fixture_id=fixture_id):
                        reasoning_output, agent_cost = await generate_reasoning_single_shot(
                            agent_client=agent_client,
                            context=ctx,
                        )
                else:
                    with timed_step("anthropic_reasoning", fixture_id=fixture_id):
                        reasoning_output, agent_cost = await generate_reasoning(
                            agent_client=agent_client,
                            football_client=client,
                            bundle=bundle,
                            fixture_id=fixture_id,
                            home_team=fx.teams.home.name,
                            away_team=fx.teams.away.name,
                            home_team_id=home_id,
                            away_team_id=away_id,
                        )

                _emit({
                    "event": "anthropic_usage",
                    "fixture_id": fixture_id,
                    "input_tokens": agent_cost.input_tokens,
                    "cache_creation_input_tokens": agent_cost.cache_creation_input_tokens,
                    "cache_read_input_tokens": agent_cost.cache_read_input_tokens,
                    "output_tokens": agent_cost.output_tokens,
                })

                upset_output = compute_upset_index(bundle, reasoning_output)

                await save_reasoning_output(
                    session, fixture_id, reasoning_output, stage.value
                )
                await save_upset_output(
                    session, fixture_id, upset_output, stage.value
                )
                await session.commit()

                reasoning_payload = _reasoning_to_dict(reasoning_output)
                upset_payload = _upset_to_dict(upset_output)
            except Exception:
                logger.exception(
                    "Reasoning generation failed for fixture %d",
                    fixture_id,
                )

    _set_cache(response, _CC_PRE_MATCH_FRESH)
    return {
        "fixture_id": fixture_id,
        "home_team": fx.teams.home.name,
        "away_team": fx.teams.away.name,
        "home_team_id": home_id,
        "away_team_id": away_id,
        "status": status,
        "stage": stage.value,
        "round": bundle.round,
        "model_version": bundle.model_version,
        "confidence": bundle.confidence,
        "cached": False,
        "predictions": {
            "winner": bundle.winner.model_dump(mode="json"),
            "total_goals": bundle.total_goals.model_dump(mode="json"),
            "ht_score": bundle.ht_score.model_dump(mode="json"),
            "first_to_score": bundle.first_to_score.model_dump(
                mode="json"
            ),
        },
        "reasoning": reasoning_payload,
        "upset": upset_payload,
    }


@router.get("/predict/live/{fixture_id}")
async def predict_live(
    fixture_id: int,
    response: Response,
    client: APIFootballClient = Depends(get_football_client),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """V1 live prediction using lambda-remaining heuristic.

    Scales pre-match expected-goals by the fraction of match time
    remaining, then combines with the current score to estimate
    regulation-time win probabilities.

    .. note::

       V1 approximation only.  A proper live model (V2) would use
       in-play xG, momentum, and red-card effects.
    """
    # ── Fetch fixture ───────────────────────────────────────────
    try:
        fx = await client.get_fixture(fixture_id)
    except APIFootballError as exc:
        _raise_for_football_error(exc)

    if fx is None:
        raise HTTPException(404, f"Fixture {fixture_id} not found")

    status = fx.fixture.status.short
    stage = detect_stage(status)

    # ── Only allow live statuses ────────────────────────────────
    if stage is FixtureStage.COMPLETED:
        latest = await get_latest_predictions_for_fixture(
            session, fixture_id
        )
        _set_cache(response, _CC_FIXTURE_COMPLETED)
        return {
            "fixture_id": fixture_id,
            "home_team": fx.teams.home.name,
            "away_team": fx.teams.away.name,
            "status": status,
            "stage": "completed",
            "message": (
                "Fixture already completed. Returning historical "
                "predictions."
            ),
            "predictions": {k: v.payload for k, v in latest.items()},
        }

    if stage is FixtureStage.NOT_PREDICTABLE:
        raise HTTPException(
            422, f"Fixture status '{status}' is not predictable"
        )

    if stage in (FixtureStage.PRE_LINEUP, FixtureStage.POST_LINEUP):
        raise HTTPException(
            422,
            "Fixture has not started. "
            "Use /predict/pre-match/{fixture_id} instead.",
        )

    # ── Current match state ─────────────────────────────────────
    elapsed = fx.fixture.status.elapsed or 0
    home_goals = fx.goals.home or 0
    away_goals = fx.goals.away or 0

    # ── Check DB cache (30s TTL, keyed by elapsed minute) ───────
    cached_row = await get_cached_live_prediction(
        session, fixture_id, elapsed
    )
    if cached_row is not None:
        _set_cache(response, _CC_LIVE_PRED)
        return {
            "fixture_id": fixture_id,
            "home_team": fx.teams.home.name,
            "away_team": fx.teams.away.name,
            "status": status,
            "stage": "live",
            "cached": True,
            "predictions": {"live_winner": cached_row.payload},
        }

    # ── Get pre-match lambdas ───────────────────────────────────
    engine = _get_engine()
    home_id = fx.teams.home.id
    away_id = fx.teams.away.id

    raw = engine.model.predict_match(home_id, away_id)
    lambda_home: float = raw["lambda_home"]
    lambda_away: float = raw["lambda_away"]

    # ── V1 heuristic ────────────────────────────────────────────
    live = derive_live_v1(
        lambda_home, lambda_away, elapsed, home_goals, away_goals
    )

    # ── Persist (append-only) ───────────────────────────────────
    await save_live_prediction(
        session, fixture_id, live, model_version="dixon_coles_v1"
    )
    await session.commit()

    logger.info(
        "Generated live prediction for fixture %d (elapsed=%d')",
        fixture_id,
        elapsed,
    )

    _set_cache(response, _CC_LIVE_PRED)
    return {
        "fixture_id": fixture_id,
        "home_team": fx.teams.home.name,
        "away_team": fx.teams.away.name,
        "status": status,
        "stage": "live",
        "confidence": raw["confidence"],
        "cached": False,
        "predictions": {"live_winner": live},
    }


@router.get("/predict/reasoning/{fixture_id}")
async def get_reasoning(
    fixture_id: int,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Return the latest reasoning for a fixture (pure DB read).

    No agent call — returns the most recent reasoning row from the DB.
    Used by the Phase 6 UI "Why" panel for lightweight re-renders.

    Returns 503 if no reasoning has been generated yet.
    """
    row = await get_latest_reasoning(session, fixture_id)
    if row is None:
        raise HTTPException(
            503,
            "No reasoning generated yet for this fixture. Retry later.",
        )
    _set_cache(response, _CC_REASONING)
    return {
        "fixture_id": fixture_id,
        "prediction_type": "reasoning",
        "generated_at": (
            row.made_at.isoformat() if row.made_at else None
        ),
        "payload": row.payload,
    }


@router.get("/predictions/history/{fixture_id}")
async def prediction_history(
    fixture_id: int,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """All predictions for a fixture, ordered by made_at DESC.

    Includes every historical row across all stages and types —
    useful for showing the prediction timeline (pre-lineup ->
    post-lineup -> live).
    """
    rows = await get_predictions_for_fixture(session, fixture_id)

    _set_cache(response, _CC_HISTORY)
    return {
        "fixture_id": fixture_id,
        "count": len(rows),
        "predictions": [
            {
                "id": str(row.id),
                "fixture_id": row.fixture_id,
                "prediction_type": row.prediction_type,
                "stage": row.stage,
                "made_at": (
                    row.made_at.isoformat() if row.made_at else None
                ),
                "payload": row.payload,
                "model_version": row.model_version,
            }
            for row in rows
        ],
    }


@router.get("/accuracy")
async def get_accuracy(
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Accuracy rollups — structured per (window, prediction_type).

    Returns an empty ``rollups`` array with an explanatory message
    when no rollups have been computed yet.
    """
    rollups = await get_all_accuracy_rollups(session)

    if not rollups:
        _set_cache(response, _CC_ACCURACY)
        return {
            "rollups": [],
            "message": "No accuracy rollups computed yet.",
        }

    _set_cache(response, _CC_ACCURACY)
    return {
        "rollups": [
            {
                "window": r.window,
                "prediction_type": r.prediction_type,
                "total_predictions": r.total_predictions,
                "brier_score": (
                    float(r.brier_score) if r.brier_score else None
                ),
                "log_loss": (
                    float(r.log_loss) if r.log_loss else None
                ),
                "top_pick_hit_rate": (
                    float(r.top_pick_hit_rate)
                    if r.top_pick_hit_rate
                    else None
                ),
                "computed_at": (
                    r.computed_at.isoformat() if r.computed_at else None
                ),
            }
            for r in rollups
        ],
    }


@router.get("/accuracy/matches")
async def get_accuracy_matches(
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Match-wise Track Record receipts — what we called vs what happened.

    One entry per fixture with an outcome, newest first, carrying the latest
    winner + total-goals picks and their actuals. Display-only; the aggregate
    /accuracy endpoint keeps the full statistical rollups.
    """
    rows = await get_evaluated_match_rows(session)
    matches = [
        build_match_receipt(outcome, winner_payload, goals_payload)
        for (outcome, winner_payload, goals_payload) in rows
    ]
    _set_cache(response, _CC_ACCURACY)
    return {"matches": matches}


# ── Pre-warm admin endpoint ──────────────────────────────────────────

_PREWARM_MAX_FIXTURES = 8


class PrewarmRequest(BaseModel):
    window_start_minutes: int = 90
    window_end_minutes: int = 150
    dry_run: bool = False


async def _verify_prewarm_key(
    authorization: str = Header(default=""),
) -> None:
    """Validate Bearer token for the pre-warm endpoint.

    Fail-closed: rejects with 503 if no key is configured, 401 if
    the header is missing/malformed, 403 if the key doesn't match.
    Uses ``secrets.compare_digest`` for timing-safe comparison.
    """
    settings = get_settings()
    if not settings.prewarm_api_key:
        _emit({
            "event": "prewarm_auth",
            "status": "key_not_configured",
        })
        raise HTTPException(503, "Pre-warm API key not configured")

    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing or malformed Authorization header")

    token = authorization[len("Bearer "):]
    if not secrets.compare_digest(token, settings.prewarm_api_key):
        raise HTTPException(403, "Invalid pre-warm API key")


async def _warm_fixtures_background(
    tick_id: str,
    window_start: datetime,
    window_end: datetime,
    dry_run: bool,
) -> None:
    """Background task: discover and warm fixtures in the kickoff window.

    Runs after the HTTP response is sent.  Uses its own DB session
    and API-Football client (the request-scoped ones are closed).
    """
    settings = get_settings()
    results: list[dict[str, Any]] = []
    counts = {
        "fixtures_in_window": 0,
        "already_warm": 0,
        "attempted": 0,
        "succeeded": 0,
        "failed": 0,
        "skipped_dry_run": 0,
    }

    try:
        # ── Build clients for background work ─────────────────────
        if not settings.api_football_key:
            _emit({
                "event": "prewarm_tick",
                "tick_id": tick_id,
                "error": "API_FOOTBALL_KEY not configured",
                **counts,
                "results": results,
            })
            return

        from backend.cache import cache as _cache_singleton
        from backend.shared.async_singleflight import AsyncSingleflight

        sf = AsyncSingleflight()

        async with APIFootballClient(
            settings.api_football_key, _cache_singleton, sf,
        ) as client:
            # ── Discover fixtures in window ───────────────────────
            all_fixtures = await client.get_fixtures(
                league=WC_LEAGUE_ID, season=WC_SEASON,
            )

            upcoming = []
            for fx in all_fixtures:
                ko = fx.fixture.date
                if ko.tzinfo is None:
                    ko = ko.replace(tzinfo=timezone.utc)
                if window_start <= ko <= window_end:
                    status = fx.fixture.status.short
                    if status in ("NS", "TBD"):
                        upcoming.append(fx)

            # Sort by soonest kickoff, cap at 8
            upcoming.sort(key=lambda f: f.fixture.date)
            upcoming = upcoming[:_PREWARM_MAX_FIXTURES]
            counts["fixtures_in_window"] = len(upcoming)

            # ── Warm each fixture sequentially ────────────────────
            for fx in upcoming:
                fixture_id = fx.fixture.id
                home_team = fx.teams.home.name
                away_team = fx.teams.away.name
                home_id = fx.teams.home.id
                away_id = fx.teams.away.id
                ko_iso = fx.fixture.date.isoformat()
                status = fx.fixture.status.short

                async with AsyncSessionLocal() as session:
                    try:
                        # ── Lineup check + stage detection ────────
                        has_lineups = False
                        if status in ("NS", "TBD"):
                            try:
                                lineups = await client.get_lineups(fixture_id)
                                has_lineups = len(lineups) > 0
                            except Exception:
                                pass

                        stage = detect_stage(status, has_lineups=has_lineups)

                        # ── Idempotency check ─────────────────────
                        cached_bundle = await get_cached_bundle(
                            session, fixture_id, stage.value,
                        )
                        cached_reasoning = await get_cached_reasoning(
                            session, fixture_id, stage.value,
                        )
                        if cached_bundle is not None and cached_reasoning is not None:
                            results.append({
                                "fixture_id": fixture_id,
                                "home_team": home_team,
                                "away_team": away_team,
                                "kickoff": ko_iso,
                                "status": "already_warm",
                            })
                            counts["already_warm"] += 1
                            continue

                        # ── dry_run: stop before LLM calls ────────
                        if dry_run:
                            results.append({
                                "fixture_id": fixture_id,
                                "home_team": home_team,
                                "away_team": away_team,
                                "kickoff": ko_iso,
                                "status": "skipped_dry_run",
                            })
                            counts["skipped_dry_run"] += 1
                            continue

                        counts["attempted"] += 1
                        t0 = time.monotonic()

                        # ── Generate predictions (same path as predict_pre_match) ──
                        _emit_unknown_round(fx.league.round, fixture_id)
                        engine = _get_engine()
                        bundle = engine.predict(
                            home_id, away_id, status,
                            has_lineups=has_lineups,
                            round_str=fx.league.round,
                        )
                        await save_prediction_bundle(session, fixture_id, bundle)
                        await session.commit()

                        # ── Reasoning (single-shot path) ──────────
                        agent_client = None
                        if settings.anthropic_api_key:
                            agent_client = AnthropicAgentClient(
                                api_key=settings.anthropic_api_key,
                            )

                        if agent_client is not None:
                            with timed_step("pre_fetch_context", fixture_id=fixture_id):
                                ctx = await pre_fetch_match_context(
                                    client=client,
                                    fixture_id=fixture_id,
                                    home_team=home_team,
                                    away_team=away_team,
                                    home_team_id=home_id,
                                    away_team_id=away_id,
                                    bundle=bundle,
                                )
                            with timed_step("anthropic_reasoning", fixture_id=fixture_id):
                                reasoning_output, agent_cost = (
                                    await generate_reasoning_single_shot(
                                        agent_client=agent_client,
                                        context=ctx,
                                    )
                                )

                            _emit({
                                "event": "anthropic_usage",
                                "fixture_id": fixture_id,
                                "source": "prewarm",
                                "input_tokens": agent_cost.input_tokens,
                                "cache_creation_input_tokens": agent_cost.cache_creation_input_tokens,
                                "cache_read_input_tokens": agent_cost.cache_read_input_tokens,
                                "output_tokens": agent_cost.output_tokens,
                            })

                            upset_output = compute_upset_index(bundle, reasoning_output)

                            await save_reasoning_output(
                                session, fixture_id, reasoning_output, stage.value,
                            )
                            await save_upset_output(
                                session, fixture_id, upset_output, stage.value,
                            )
                            await session.commit()

                        duration_ms = round((time.monotonic() - t0) * 1000, 1)
                        results.append({
                            "fixture_id": fixture_id,
                            "home_team": home_team,
                            "away_team": away_team,
                            "kickoff": ko_iso,
                            "status": "warmed",
                            "duration_ms": duration_ms,
                        })
                        counts["succeeded"] += 1

                    except Exception as exc:
                        logger.exception(
                            "Pre-warm failed for fixture %d", fixture_id,
                        )
                        import sentry_sdk as _sentry
                        if _sentry.is_initialized():
                            with _sentry.new_scope() as scope:
                                scope.set_tag("fixture_id", str(fixture_id))
                                scope.set_context("prewarm", {
                                    "tick_id": tick_id,
                                    "home_team": home_team,
                                    "away_team": away_team,
                                    "kickoff": ko_iso,
                                })
                                _sentry.capture_exception(exc)
                        results.append({
                            "fixture_id": fixture_id,
                            "home_team": home_team,
                            "away_team": away_team,
                            "kickoff": ko_iso,
                            "status": "failed",
                            "error": f"{type(exc).__name__}: {exc}",
                        })
                        counts["failed"] += 1

    except Exception as exc:
        logger.exception("Pre-warm tick failed globally")
        _emit({
            "event": "prewarm_tick",
            "tick_id": tick_id,
            "error": f"{type(exc).__name__}: {exc}",
            **counts,
            "results": results,
        })
        return

    _emit({
        "event": "prewarm_tick",
        "tick_id": tick_id,
        "window": {
            "start": window_start.isoformat(),
            "end": window_end.isoformat(),
        },
        "dry_run": dry_run,
        **counts,
        "results": results,
    })


@router.post("/admin/prewarm/upcoming")
async def prewarm_upcoming(
    body: PrewarmRequest,
    background_tasks: BackgroundTasks,
    _auth: None = Depends(_verify_prewarm_key),
) -> dict:
    """Trigger pre-warming of upcoming fixtures.

    Returns immediately with an ack.  Fixture warming runs in a
    background task after the response is sent.
    """
    now = datetime.now(timezone.utc)
    window_start = now + timedelta(minutes=body.window_start_minutes)
    window_end = now + timedelta(minutes=body.window_end_minutes)
    tick_id = str(uuid.uuid4())

    background_tasks.add_task(
        _warm_fixtures_background,
        tick_id=tick_id,
        window_start=window_start,
        window_end=window_end,
        dry_run=body.dry_run,
    )

    return {
        "tick_id": tick_id,
        "accepted": True,
        "dry_run": body.dry_run,
        "window": {
            "start": window_start.isoformat(),
            "end": window_end.isoformat(),
        },
    }
