"""Accuracy rollup script for football predictions.

Joins predictions with outcomes, computes per-type accuracy metrics
(Brier score, log-loss, top-pick hit rate) across multiple time
windows, and INSERTs results into ``football.accuracy_rollups``.

**Append-only**: every run INSERTs new rows, never UPDATEs.

Usage::

    python -m backend.football.scripts.compute_accuracy

Exit codes
----------
- 0  -- success (including "no settled fixtures, 0 rollups computed")
- 1  -- unexpected error during computation
"""

from __future__ import annotations

import asyncio
import logging
import math
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Callable

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.shared.db import get_db_session
from backend.shared.models import AccuracyRollup, Outcome, Prediction

logger = logging.getLogger(__name__)

# Prediction types eligible for accuracy computation.
# Excludes "live_winner" — live predictions are evaluated separately.
ACCURACY_PRED_TYPES: tuple[str, ...] = (
    "winner",
    "total_goals",
    "ht_score",
    "first_to_score",
)

# Tournament window (hardcoded for FIFA WC 2026).
TOURNAMENT_START = datetime(2026, 6, 11, tzinfo=timezone.utc)
TOURNAMENT_END = datetime(2026, 7, 19, 23, 59, 59, tzinfo=timezone.utc)

# Epsilon to avoid log(0) in log-loss computation.
LOG_LOSS_EPS = 1e-15


# ── Intermediate result holder ────────────────────────────────────────


@dataclass
class RollupMetrics:
    """Intermediate holder for computed accuracy metrics."""

    total_predictions: int
    brier_score: float | None
    log_loss: float | None
    top_pick_hit_rate: float | None


# ── Data fetching ─────────────────────────────────────────────────────


async def _fetch_prediction_outcome_pairs(
    session: AsyncSession,
) -> list[tuple[Prediction, Outcome]]:
    """Fetch the latest prediction per (fixture_id, prediction_type)
    joined with its outcome.

    Uses a correlated subquery (max ``made_at`` per group) to pick
    exactly one prediction per type per fixture — the most recent.
    Only includes the four accuracy-eligible prediction types.
    """
    latest_sub = (
        select(
            Prediction.fixture_id,
            Prediction.prediction_type,
            func.max(Prediction.made_at).label("max_made_at"),
        )
        .where(Prediction.prediction_type.in_(ACCURACY_PRED_TYPES))
        .group_by(Prediction.fixture_id, Prediction.prediction_type)
        .subquery()
    )

    stmt = (
        select(Prediction, Outcome)
        .join(
            latest_sub,
            and_(
                Prediction.fixture_id == latest_sub.c.fixture_id,
                Prediction.prediction_type == latest_sub.c.prediction_type,
                Prediction.made_at == latest_sub.c.max_made_at,
            ),
        )
        .join(
            Outcome,
            Prediction.fixture_id == Outcome.fixture_id,
        )
    )

    result = await session.execute(stmt)
    return [(row[0], row[1]) for row in result.all()]


# ── Window filters ────────────────────────────────────────────────────

WindowFilter = Callable[[Prediction, Outcome], bool]


def _make_window_filters() -> dict[str, WindowFilter]:
    """Return filters keyed by window name.

    ``now`` is captured once so all windows use a consistent timestamp.
    """
    now = datetime.now(timezone.utc)
    return {
        "all_time": lambda _p, _o: True,
        "last_7d": lambda p, _o: p.made_at >= now - timedelta(days=7),
        "last_30d": lambda p, _o: p.made_at >= now - timedelta(days=30),
        "tournament": lambda _p, o: (
            TOURNAMENT_START <= o.kickoff_at <= TOURNAMENT_END
        ),
    }


# ── Per-type metric computation (pure Python, no DB) ──────────────────


def _compute_winner_metrics(
    pairs: list[tuple[Prediction, Outcome]],
) -> RollupMetrics:
    """Brier + log-loss + top-pick hit rate for 3-way winner."""
    if not pairs:
        return RollupMetrics(0, None, None, None)

    brier_total = 0.0
    ll_total = 0.0
    hits = 0

    for pred, outcome in pairs:
        payload = pred.payload
        predicted = [
            float(payload["p_home_win"]),
            float(payload["p_draw"]),
            float(payload["p_away_win"]),
        ]

        if outcome.ft_home > outcome.ft_away:
            actual = [1.0, 0.0, 0.0]
        elif outcome.ft_home == outcome.ft_away:
            actual = [0.0, 1.0, 0.0]
        else:
            actual = [0.0, 0.0, 1.0]

        brier_total += sum(
            (p - a) ** 2 for p, a in zip(predicted, actual)
        )
        ll_total += -sum(
            a * math.log(max(p, LOG_LOSS_EPS))
            for p, a in zip(predicted, actual)
        )

        top_pick_idx = predicted.index(max(predicted))
        if actual[top_pick_idx] == 1.0:
            hits += 1

    n = len(pairs)
    return RollupMetrics(
        total_predictions=n,
        brier_score=brier_total / n,
        log_loss=ll_total / n,
        top_pick_hit_rate=hits / n,
    )


def _compute_total_goals_metrics(
    pairs: list[tuple[Prediction, Outcome]],
) -> RollupMetrics:
    """Brier + log-loss on the over/under 2.5 goals line."""
    if not pairs:
        return RollupMetrics(0, None, None, None)

    brier_total = 0.0
    ll_total = 0.0
    hits = 0

    for pred, outcome in pairs:
        payload = pred.payload
        p_over = float(payload["over_2_5"])
        p_under = float(payload["under_2_5"])

        total_goals = outcome.ft_home + outcome.ft_away
        actual_over = 1.0 if total_goals > 2.5 else 0.0
        actual_under = 1.0 - actual_over

        brier_total += (p_over - actual_over) ** 2 + (
            p_under - actual_under
        ) ** 2
        ll_total += -(
            actual_over * math.log(max(p_over, LOG_LOSS_EPS))
            + actual_under * math.log(max(p_under, LOG_LOSS_EPS))
        )

        predicted_over = p_over >= 0.5
        actual_was_over = actual_over == 1.0
        if predicted_over == actual_was_over:
            hits += 1

    n = len(pairs)
    return RollupMetrics(
        total_predictions=n,
        brier_score=brier_total / n,
        log_loss=ll_total / n,
        top_pick_hit_rate=hits / n,
    )


def _compute_ht_score_metrics(
    pairs: list[tuple[Prediction, Outcome]],
) -> RollupMetrics:
    """Top-pick hit rate only for HT score.  Brier / log-loss = NULL.

    Skips outcomes where ``ht_home`` or ``ht_away`` is NULL.
    """
    eligible = [
        (p, o)
        for p, o in pairs
        if o.ht_home is not None and o.ht_away is not None
    ]

    if not eligible:
        return RollupMetrics(0, None, None, None)

    hits = 0
    for pred, outcome in eligible:
        matrix = pred.payload["ht_scoreline_matrix"]

        max_val = -1.0
        max_h, max_a = 0, 0
        for h_idx, row in enumerate(matrix):
            for a_idx, val in enumerate(row):
                if val > max_val:
                    max_val = val
                    max_h, max_a = h_idx, a_idx

        if max_h == outcome.ht_home and max_a == outcome.ht_away:
            hits += 1

    n = len(eligible)
    return RollupMetrics(
        total_predictions=n,
        brier_score=None,
        log_loss=None,
        top_pick_hit_rate=hits / n,
    )


def _compute_first_to_score_metrics(
    pairs: list[tuple[Prediction, Outcome]],
) -> RollupMetrics:
    """Brier + log-loss + top-pick for first-to-score.

    **Excludes** predictions where ``outcome.first_scorer_team`` is
    NULL.  When all are excluded, returns n=0 and all metrics NULL.
    """
    eligible = [
        (p, o) for p, o in pairs if o.first_scorer_team is not None
    ]

    if not eligible:
        return RollupMetrics(0, None, None, None)

    brier_total = 0.0
    ll_total = 0.0
    hits = 0

    for pred, outcome in eligible:
        payload = pred.payload
        predicted = [
            float(payload["p_home_first"]),
            float(payload["p_away_first"]),
            float(payload["p_no_goals"]),
        ]

        fst = outcome.first_scorer_team.lower()
        if fst == outcome.home_team.lower():
            actual = [1.0, 0.0, 0.0]
        elif fst == outcome.away_team.lower():
            actual = [0.0, 1.0, 0.0]
        else:
            actual = [0.0, 0.0, 1.0]

        brier_total += sum(
            (p - a) ** 2 for p, a in zip(predicted, actual)
        )
        ll_total += -sum(
            a * math.log(max(p, LOG_LOSS_EPS))
            for p, a in zip(predicted, actual)
        )

        top_pick_idx = predicted.index(max(predicted))
        if actual[top_pick_idx] == 1.0:
            hits += 1

    n = len(eligible)
    return RollupMetrics(
        total_predictions=n,
        brier_score=brier_total / n,
        log_loss=ll_total / n,
        top_pick_hit_rate=hits / n,
    )


# ── Dispatch ──────────────────────────────────────────────────────────

_METRIC_COMPUTERS: dict[
    str,
    Callable[[list[tuple[Prediction, Outcome]]], RollupMetrics],
] = {
    "winner": _compute_winner_metrics,
    "total_goals": _compute_total_goals_metrics,
    "ht_score": _compute_ht_score_metrics,
    "first_to_score": _compute_first_to_score_metrics,
}


# ── Orchestration ─────────────────────────────────────────────────────


async def _run() -> int:
    """Compute accuracy rollups.  Returns 0 on success."""
    async with get_db_session() as session:
        pairs = await _fetch_prediction_outcome_pairs(session)

    if not pairs:
        logger.info("No settled fixtures found, 0 rollups computed.")
        print("No settled fixtures, 0 rollups computed.")
        return 0

    logger.info("Fetched %d prediction-outcome pairs.", len(pairs))

    # Group by prediction_type.
    by_type: dict[str, list[tuple[Prediction, Outcome]]] = {}
    for pred, outcome in pairs:
        by_type.setdefault(pred.prediction_type, []).append(
            (pred, outcome)
        )

    # Compute metrics for each (window, prediction_type).
    window_filters = _make_window_filters()
    rollup_rows: list[AccuracyRollup] = []

    for window_name, window_filter in window_filters.items():
        for pred_type in ACCURACY_PRED_TYPES:
            type_pairs = by_type.get(pred_type, [])
            filtered = [
                (p, o)
                for p, o in type_pairs
                if window_filter(p, o)
            ]

            compute_fn = _METRIC_COMPUTERS[pred_type]
            metrics = compute_fn(filtered)

            row = AccuracyRollup(
                window=window_name,
                prediction_type=pred_type,
                total_predictions=metrics.total_predictions,
                brier_score=(
                    Decimal(str(round(metrics.brier_score, 4)))
                    if metrics.brier_score is not None
                    else None
                ),
                log_loss=(
                    Decimal(str(round(metrics.log_loss, 4)))
                    if metrics.log_loss is not None
                    else None
                ),
                top_pick_hit_rate=(
                    Decimal(str(round(metrics.top_pick_hit_rate, 3)))
                    if metrics.top_pick_hit_rate is not None
                    else None
                ),
            )
            rollup_rows.append(row)

            logger.info(
                "  %s / %-15s  n=%-4d  brier=%s  log_loss=%s  hit=%s",
                window_name,
                pred_type,
                metrics.total_predictions,
                (
                    f"{metrics.brier_score:.4f}"
                    if metrics.brier_score is not None
                    else "NULL"
                ),
                (
                    f"{metrics.log_loss:.4f}"
                    if metrics.log_loss is not None
                    else "NULL"
                ),
                (
                    f"{metrics.top_pick_hit_rate:.3f}"
                    if metrics.top_pick_hit_rate is not None
                    else "NULL"
                ),
            )

    # Persist (append-only).
    async with get_db_session() as session:
        session.add_all(rollup_rows)
        await session.commit()

    non_zero = sum(1 for r in rollup_rows if r.total_predictions > 0)
    print(
        f"\nAccuracy rollup complete: {len(rollup_rows)} rows inserted "
        f"({non_zero} with data, "
        f"{len(rollup_rows) - non_zero} with n=0)."
    )
    return 0


# ── Entry point ───────────────────────────────────────────────────────


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-5s %(name)s: %(message)s",
    )
    try:
        exit_code = asyncio.run(_run())
    except Exception:
        logger.exception("Accuracy rollup failed")
        exit_code = 1
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
