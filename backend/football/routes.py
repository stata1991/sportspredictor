"""Football API routes.

Mounted at ``/api/football`` by main.py.
"""

from __future__ import annotations

import logging
from typing import Any, NoReturn

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.football.agent.client import AnthropicAgentClient
from backend.football.agent.reasoning import ReasoningOutput, generate_reasoning
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
from backend.football.persistence import (
    get_all_accuracy_rollups,
    get_cached_bundle,
    get_cached_live_prediction,
    get_cached_reasoning,
    get_latest_predictions_for_fixture,
    get_latest_reasoning,
    get_predictions_for_fixture,
    save_live_prediction,
    save_prediction_bundle,
    save_reasoning_output,
    save_upset_output,
)
from backend.football.predictions.derivations import derive_live_v1
from backend.football.predictions.engine import (
    PredictionEngine,
    detect_stage,
)
from backend.football.predictions.schemas import FixtureStage
from backend.football.schemas import CoverageStatus
from backend.shared.db import get_session

logger = logging.getLogger(__name__)

router = APIRouter()

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
    league: int = WC_LEAGUE_ID,
    season: int = WC_SEASON,
    client: APIFootballClient = Depends(get_football_client),
) -> dict:
    """List all fixtures for a league/season."""
    try:
        fixtures = await client.get_fixtures(league=league, season=season)
    except APIFootballError as exc:
        _raise_for_football_error(exc)

    return {
        "count": len(fixtures),
        "fixtures": [fx.model_dump(mode="json") for fx in fixtures],
    }


@router.get("/fixtures/{fixture_id}")
async def get_fixture(
    fixture_id: int,
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
    return fixture.model_dump(mode="json")


@router.get("/coverage")
async def get_coverage(
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
    status = CoverageStatus.from_af_coverage(cov)
    return status.model_dump()


# ── Prediction endpoints ─────────────────────────────────────────────


@router.get("/predict/pre-match/{fixture_id}")
async def predict_pre_match(
    fixture_id: int,
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
    try:
        fx = await client.get_fixture(fixture_id)
    except APIFootballError as exc:
        _raise_for_football_error(exc)

    if fx is None:
        raise HTTPException(404, f"Fixture {fixture_id} not found")

    status = fx.fixture.status.short
    home_id = fx.teams.home.id
    away_id = fx.teams.away.id

    # ── Check lineups for NS/TBD fixtures ───────────────────────
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
        return {
            "fixture_id": fixture_id,
            "home_team": fx.teams.home.name,
            "away_team": fx.teams.away.name,
            "status": status,
            "stage": "completed",
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

        return {
            "fixture_id": fixture_id,
            "home_team": fx.teams.home.name,
            "away_team": fx.teams.away.name,
            "status": status,
            "stage": stage.value,
            "cached": True,
            "predictions": {k: v.payload for k, v in cached.items()},
            "reasoning": reasoning_payload,
            "upset": upset_payload,
        }

    # ── Generate fresh predictions ──────────────────────────────
    engine = _get_engine()
    bundle = engine.predict(home_id, away_id, status, has_lineups=has_lineups)

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
                reasoning_output = await generate_reasoning(
                    agent_client=agent_client,
                    football_client=client,
                    bundle=bundle,
                    fixture_id=fixture_id,
                    home_team=fx.teams.home.name,
                    away_team=fx.teams.away.name,
                    home_team_id=home_id,
                    away_team_id=away_id,
                )
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

    return {
        "fixture_id": fixture_id,
        "home_team": fx.teams.home.name,
        "away_team": fx.teams.away.name,
        "status": status,
        "stage": stage.value,
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
    session: AsyncSession = Depends(get_session),
) -> dict:
    """All predictions for a fixture, ordered by made_at DESC.

    Includes every historical row across all stages and types —
    useful for showing the prediction timeline (pre-lineup ->
    post-lineup -> live).
    """
    rows = await get_predictions_for_fixture(session, fixture_id)

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
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Accuracy rollups — structured per (window, prediction_type).

    Returns an empty ``rollups`` array with an explanatory message
    when no rollups have been computed yet.
    """
    rollups = await get_all_accuracy_rollups(session)

    if not rollups:
        return {
            "rollups": [],
            "message": "No accuracy rollups computed yet.",
        }

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
