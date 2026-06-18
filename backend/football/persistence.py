"""Persistence layer for football predictions and outcomes.

Five core functions — no business logic, no model evaluation.

**Append-only contract on predictions**: there is deliberately no
``update_prediction`` function.  If a prediction changes (lineup
released, live update), the caller INSERTs a new row via
``save_prediction_bundle``.  The ``made_at`` timestamp provides the
audit trail.

**Upsert contract on outcomes**: ``save_outcome`` uses
``INSERT … ON CONFLICT DO UPDATE`` so re-ingesting a fixture after
corrections (e.g. AET → regulation score fix) is idempotent.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import and_, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.football.predictions.schemas import PredictionBundle
from backend.shared.models import AccuracyRollup, Outcome, Prediction

logger = logging.getLogger(__name__)

# The four prediction types, matching PredictionBundle attribute names.
PREDICTION_TYPES: tuple[str, ...] = (
    "winner",
    "total_goals",
    "ht_score",
    "first_to_score",
)


# ── Predictions (append-only) ────────────────────────────────────────


async def save_prediction_bundle(
    session: AsyncSession,
    fixture_id: int,
    bundle: PredictionBundle,
) -> list[Prediction]:
    """Persist all four prediction types from a bundle.

    Creates four ``Prediction`` rows (one per type) via INSERT.
    **Never updates existing rows** — this is the append-only guarantee.

    Parameters
    ----------
    session:
        Active async session (caller manages commit/rollback).
    fixture_id:
        API-Football fixture ID.
    bundle:
        :class:`PredictionBundle` from the prediction engine.

    Returns
    -------
    List of four flushed (but not yet committed) ``Prediction`` rows.
    """
    rows: list[Prediction] = []
    for pred_type in PREDICTION_TYPES:
        payload_model = getattr(bundle, pred_type)
        row = Prediction(
            fixture_id=fixture_id,
            prediction_type=pred_type,
            stage=bundle.stage.value,
            payload=payload_model.model_dump(mode="json"),
            model_version=bundle.model_version,
        )
        rows.append(row)

    session.add_all(rows)
    await session.flush()

    logger.info(
        "Saved %d predictions for fixture %d (stage=%s, model=%s)",
        len(rows),
        fixture_id,
        bundle.stage.value,
        bundle.model_version,
    )
    return rows


async def get_predictions_for_fixture(
    session: AsyncSession,
    fixture_id: int,
) -> list[Prediction]:
    """Fetch all predictions for a fixture, newest first.

    Returns every historical prediction row — useful for showing the
    prediction timeline (pre-lineup → post-lineup → live).
    """
    stmt = (
        select(Prediction)
        .where(Prediction.fixture_id == fixture_id)
        .order_by(Prediction.made_at.desc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_latest_predictions_for_fixture(
    session: AsyncSession,
    fixture_id: int,
) -> dict[str, Prediction]:
    """Fetch the most recent prediction per type for a fixture.

    Uses a correlated subquery (max ``made_at`` per ``prediction_type``)
    to select exactly one row per type — the latest one.

    Returns
    -------
    Dict mapping ``prediction_type`` → ``Prediction``.  Missing types
    are simply absent from the dict.
    """
    # Subquery: latest made_at per prediction_type for this fixture.
    latest = (
        select(
            Prediction.prediction_type,
            func.max(Prediction.made_at).label("max_made_at"),
        )
        .where(Prediction.fixture_id == fixture_id)
        .group_by(Prediction.prediction_type)
        .subquery()
    )

    stmt = select(Prediction).join(
        latest,
        (Prediction.prediction_type == latest.c.prediction_type)
        & (Prediction.made_at == latest.c.max_made_at)
        & (Prediction.fixture_id == fixture_id),
    )
    result = await session.execute(stmt)
    return {row.prediction_type: row for row in result.scalars().all()}


async def get_upsets_above_threshold(
    session: AsyncSession,
    threshold: float = 0.45,
) -> list[Prediction]:
    """Latest upset_index prediction per fixture where upset_index >= threshold.

    Uses a subquery to find the most recent ``made_at`` per fixture for
    ``prediction_type='upset_index'``, then filters by threshold on the
    joined rows.

    Returns Prediction rows ordered by ``upset_index`` descending.
    Status filtering (upcoming vs completed) is the caller's concern —
    fixture status lives in API-Football data, not the predictions table.
    """
    threshold_decimal = Decimal(str(threshold))

    # Subquery: latest made_at per fixture for upset_index predictions.
    latest = (
        select(
            Prediction.fixture_id,
            func.max(Prediction.made_at).label("max_made_at"),
        )
        .where(Prediction.prediction_type == "upset_index")
        .group_by(Prediction.fixture_id)
        .subquery()
    )

    stmt = (
        select(Prediction)
        .join(
            latest,
            (Prediction.fixture_id == latest.c.fixture_id)
            & (Prediction.made_at == latest.c.max_made_at)
            & (Prediction.prediction_type == "upset_index"),
        )
        .where(Prediction.upset_index >= threshold_decimal)
        .order_by(Prediction.upset_index.desc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


# ── Outcomes (upsert) ────────────────────────────────────────────────


async def save_outcome(
    session: AsyncSession,
    *,
    fixture_id: int,
    home_team: str,
    away_team: str,
    ft_home: int,
    ft_away: int,
    ht_home: int | None = None,
    ht_away: int | None = None,
    first_scorer_team: str | None = None,
    round: str | None = None,
    advancer_team: str | None = None,
    decided_by: str | None = None,
    kickoff_at: datetime,
) -> None:
    """Upsert a match outcome.

    Uses ``INSERT … ON CONFLICT (fixture_id) DO UPDATE`` so
    re-ingesting a fixture (e.g. after AET score correction) is
    idempotent.

    Parameters
    ----------
    session:
        Active async session (caller manages commit/rollback).
    fixture_id … kickoff_at:
        Outcome fields.  ``ht_home``/``ht_away`` are nullable for
        matches where HT data is unavailable. ``advancer_team`` /
        ``decided_by`` are set only for knockout fixtures (EVAL-2);
        group-stage rows leave them ``None``.
    """
    insert_values = dict(
        fixture_id=fixture_id,
        home_team=home_team,
        away_team=away_team,
        ft_home=ft_home,
        ft_away=ft_away,
        ht_home=ht_home,
        ht_away=ht_away,
        first_scorer_team=first_scorer_team,
        round=round,
        advancer_team=advancer_team,
        decided_by=decided_by,
        kickoff_at=kickoff_at,
    )

    # Fields to update on conflict (everything except the PK).
    update_fields = {
        k: v for k, v in insert_values.items() if k != "fixture_id"
    }
    update_fields["settled_at"] = func.now()

    stmt = (
        pg_insert(Outcome)
        .values(**insert_values)
        .on_conflict_do_update(
            index_elements=[Outcome.fixture_id],
            set_=update_fields,
        )
    )
    await session.execute(stmt)
    await session.flush()

    logger.info(
        "Upserted outcome for fixture %d: %s %d–%d %s",
        fixture_id,
        home_team,
        ft_home,
        ft_away,
        away_team,
    )


async def get_outcome(
    session: AsyncSession,
    fixture_id: int,
) -> Outcome | None:
    """Fetch the outcome for a fixture, or ``None`` if not yet settled."""
    stmt = select(Outcome).where(Outcome.fixture_id == fixture_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


# ── Live prediction (append-only, short TTL) ─────────────────────────

LIVE_CACHE_MAX_AGE_SECONDS = 30  # 30-second window for live predictions


async def save_live_prediction(
    session: AsyncSession,
    fixture_id: int,
    payload: dict,
    model_version: str = "dixon_coles_v1",
) -> Prediction:
    """Persist a single live prediction row (append-only).

    Parameters
    ----------
    session:
        Active async session (caller manages commit/rollback).
    fixture_id:
        API-Football fixture ID.
    payload:
        The live prediction dict (must include ``elapsed`` key).
    model_version:
        Model identifier string.

    Returns
    -------
    Flushed (but not yet committed) ``Prediction`` row.
    """
    row = Prediction(
        fixture_id=fixture_id,
        prediction_type="live_winner",
        stage="live",
        payload=payload,
        model_version=model_version,
    )
    session.add(row)
    await session.flush()

    logger.info(
        "Saved live prediction for fixture %d (elapsed=%s)",
        fixture_id,
        payload.get("elapsed"),
    )
    return row


async def get_cached_live_prediction(
    session: AsyncSession,
    fixture_id: int,
    elapsed: int,
    max_age_seconds: int = LIVE_CACHE_MAX_AGE_SECONDS,
) -> Prediction | None:
    """Check for a fresh live prediction at the given elapsed minute.

    The cache key is (fixture_id, elapsed minute, recency).  A
    prediction at 23' is distinct from one at 24', so advancing a
    minute always triggers a fresh computation even within the 30-second
    TTL window.

    .. note::

       ``elapsed=45`` is ambiguous — it can mean first-half injury
       time *or* the start of the second half.  API-Football reports
       both as 45.  This is acceptable for V1 because the 30-second
       TTL means we recompute frequently anyway, but a V2 model
       should disambiguate via the ``status.short`` field (1H vs 2H).

    Returns the cached ``Prediction`` row, or ``None`` if stale /
    missing / wrong minute.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=max_age_seconds)
    stmt = (
        select(Prediction)
        .where(
            Prediction.fixture_id == fixture_id,
            Prediction.stage == "live",
            Prediction.prediction_type == "live_winner",
            Prediction.made_at >= cutoff,
        )
        .order_by(Prediction.made_at.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()

    if row is None:
        return None

    # Elapsed minute must match — a prediction at 23' ≠ 24'.
    if row.payload.get("elapsed") != elapsed:
        return None

    return row


# ── Live narration read (STATS-B, append-only) ───────────────────────


async def save_live_narration(
    session: AsyncSession,
    fixture_id: int,
    payload: dict,
    model_version: str = "live_note_v1",
) -> Prediction:
    """Persist one live in-play narration read (append-only).

    Reuses the generic ``Prediction`` table with
    ``prediction_type="live_narration"`` — no schema change. The payload
    carries the narration text plus the trigger/lean state it was
    generated against, so LEAN-CROSS can diff against the last read and
    re-polls reuse it verbatim. ``made_at`` drives the min-interval floor.
    """
    row = Prediction(
        fixture_id=fixture_id,
        prediction_type="live_narration",
        stage="live",
        payload=payload,
        model_version=model_version,
    )
    session.add(row)
    await session.flush()

    logger.info(
        "Saved live narration for fixture %d (trigger=%s, lean=%s)",
        fixture_id,
        payload.get("trigger"),
        payload.get("leaning_side"),
    )
    return row


async def get_latest_live_narration(
    session: AsyncSession,
    fixture_id: int,
) -> Prediction | None:
    """Fetch the most recent live narration read for a fixture (no TTL).

    Used both to diff trigger/lean state on each poll tick and to reuse
    the persisted read verbatim between triggers.
    """
    stmt = (
        select(Prediction)
        .where(
            Prediction.fixture_id == fixture_id,
            Prediction.prediction_type == "live_narration",
        )
        .order_by(Prediction.made_at.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


# ── Prediction cache (stage-aware freshness) ─────────────────────────

CACHE_MAX_AGE_SECONDS = 3600  # 1 hour


async def get_cached_bundle(
    session: AsyncSession,
    fixture_id: int,
    stage: str,
    max_age_seconds: int = CACHE_MAX_AGE_SECONDS,
) -> dict[str, Prediction] | None:
    """Check for a fresh, complete prediction set at a given stage.

    Returns a dict mapping ``prediction_type`` → ``Prediction`` if all
    four types exist and the newest was made within *max_age_seconds*.
    Returns ``None`` if the bundle is stale or incomplete.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=max_age_seconds)
    stmt = (
        select(Prediction)
        .where(
            Prediction.fixture_id == fixture_id,
            Prediction.stage == stage,
            Prediction.prediction_type.in_(PREDICTION_TYPES),
            Prediction.made_at >= cutoff,
        )
        .order_by(Prediction.made_at.desc())
    )
    result = await session.execute(stmt)
    rows = list(result.scalars().all())

    # Keep the latest row per prediction_type.
    by_type: dict[str, Prediction] = {}
    for row in rows:
        if row.prediction_type not in by_type:
            by_type[row.prediction_type] = row

    if set(by_type.keys()) != set(PREDICTION_TYPES):
        return None

    return by_type


# ── Reasoning + upset persistence ─────────────────────────────────────

REASONING_TYPES = ("reasoning", "upset_index")


async def save_reasoning_output(
    session: AsyncSession,
    fixture_id: int,
    reasoning_output: object,
    stage: str,
) -> Prediction:
    """Persist reasoning output as a Prediction row.

    Parameters
    ----------
    session:
        Active async session (caller manages commit).
    fixture_id:
        API-Football fixture ID.
    reasoning_output:
        :class:`ReasoningOutput` from the reasoning module.
    stage:
        Current prediction stage (e.g. "pre_lineup").

    Returns
    -------
    Flushed (not committed) Prediction row.
    """
    # Build payload — exclude internal fields not useful in the API response.
    payload = reasoning_output.model_dump(mode="json")
    payload.pop("generated_at", None)
    payload.pop("cost_usd", None)
    payload.pop("tokens_used", None)

    row = Prediction(
        fixture_id=fixture_id,
        prediction_type="reasoning",
        stage=stage,
        payload=payload,
        model_version=reasoning_output.model_version,
    )
    session.add(row)
    await session.flush()

    logger.info(
        "Saved reasoning for fixture %d (stage=%s, status=%s)",
        fixture_id,
        stage,
        reasoning_output.validation_status,
    )
    return row


async def save_upset_output(
    session: AsyncSession,
    fixture_id: int,
    upset_output: object,
    stage: str,
) -> Prediction:
    """Persist upset index output as a Prediction row.

    Parameters
    ----------
    session:
        Active async session (caller manages commit).
    fixture_id:
        API-Football fixture ID.
    upset_output:
        :class:`UpsetOutput` from the upset module.
    stage:
        Current prediction stage.

    Returns
    -------
    Flushed (not committed) Prediction row.
    """
    payload = {
        "upset_index": upset_output.upset_index,
        "deterministic_component": upset_output.deterministic_component,
        "agent_component": upset_output.agent_component,
        "bounded_agent": upset_output.bounded_agent,
        "upset_signals": [
            {"signal": s.signal, "direction": s.direction, "source": s.source}
            for s in upset_output.upset_signals
        ],
        "upset_paths": upset_output.upset_paths,
    }

    row = Prediction(
        fixture_id=fixture_id,
        prediction_type="upset_index",
        stage=stage,
        payload=payload,
        model_version="hybrid_v1",
        upset_index=Decimal(str(round(upset_output.upset_index, 2))),
    )
    session.add(row)
    await session.flush()

    logger.info(
        "Saved upset_index=%.4f for fixture %d (stage=%s)",
        upset_output.upset_index,
        fixture_id,
        stage,
    )
    return row


async def get_cached_reasoning(
    session: AsyncSession,
    fixture_id: int,
    stage: str,
    max_age_seconds: int = CACHE_MAX_AGE_SECONDS,
) -> dict[str, Prediction] | None:
    """Check for fresh reasoning + upset_index rows at a given stage.

    Returns a dict ``{"reasoning": row, "upset_index": row}`` if both
    exist and are within the TTL.  Returns ``None`` otherwise.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=max_age_seconds)
    stmt = (
        select(Prediction)
        .where(
            Prediction.fixture_id == fixture_id,
            Prediction.stage == stage,
            Prediction.prediction_type.in_(REASONING_TYPES),
            Prediction.made_at >= cutoff,
        )
        .order_by(Prediction.made_at.desc())
    )
    result = await session.execute(stmt)
    rows = list(result.scalars().all())

    by_type: dict[str, Prediction] = {}
    for row in rows:
        if row.prediction_type not in by_type:
            by_type[row.prediction_type] = row

    if set(by_type.keys()) != set(REASONING_TYPES):
        return None

    return by_type


async def get_latest_reasoning(
    session: AsyncSession,
    fixture_id: int,
) -> Prediction | None:
    """Fetch the most recent reasoning row for a fixture (no TTL).

    Used by the ``/predict/reasoning/{fixture_id}`` endpoint for
    lightweight UI re-renders.
    """
    stmt = (
        select(Prediction)
        .where(
            Prediction.fixture_id == fixture_id,
            Prediction.prediction_type == "reasoning",
        )
        .order_by(Prediction.made_at.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


# ── Accuracy rollups ─────────────────────────────────────────────────


async def get_evaluated_match_rows(
    session: AsyncSession,
) -> list[tuple[Outcome, dict | None, dict | None]]:
    """Per fixture with an outcome: ``(outcome, winner_payload, goals_payload)``,
    newest first (by kickoff).

    The payloads are the latest ``winner`` / ``total_goals`` prediction for the
    fixture (None if absent). Powers the Track Record match-wise receipts.
    """
    display_types = ("winner", "total_goals")

    latest_sub = (
        select(
            Prediction.fixture_id,
            Prediction.prediction_type,
            func.max(Prediction.made_at).label("max_made_at"),
        )
        .where(Prediction.prediction_type.in_(display_types))
        .group_by(Prediction.fixture_id, Prediction.prediction_type)
        .subquery()
    )
    pred_stmt = select(Prediction).join(
        latest_sub,
        and_(
            Prediction.fixture_id == latest_sub.c.fixture_id,
            Prediction.prediction_type == latest_sub.c.prediction_type,
            Prediction.made_at == latest_sub.c.max_made_at,
        ),
    )
    preds = (await session.execute(pred_stmt)).scalars().all()

    by_fixture: dict[int, dict[str, dict]] = {}
    for p in preds:
        by_fixture.setdefault(p.fixture_id, {})[p.prediction_type] = p.payload

    outcomes = (
        await session.execute(
            select(Outcome).order_by(Outcome.kickoff_at.desc())
        )
    ).scalars().all()

    return [
        (o, by_fixture.get(o.fixture_id, {}).get("winner"),
         by_fixture.get(o.fixture_id, {}).get("total_goals"))
        for o in outcomes
    ]


async def get_all_accuracy_rollups(
    session: AsyncSession,
) -> list[AccuracyRollup]:
    """Fetch the latest rollup per (window, prediction_type).

    ``compute_accuracy`` now replaces the grid in place, so there is normally
    exactly one row per cell. The ``DISTINCT ON`` keeps this correct as
    defence-in-depth against any historical duplicate rows — it returns only
    the most recent (max ``computed_at``) row per (window, prediction_type).
    """
    stmt = (
        select(AccuracyRollup)
        .order_by(
            AccuracyRollup.window,
            AccuracyRollup.prediction_type,
            AccuracyRollup.computed_at.desc(),
        )
        .distinct(
            AccuracyRollup.window,
            AccuracyRollup.prediction_type,
        )
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())
