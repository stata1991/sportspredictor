"""Outcome ingestion script for football predictions.

Fetches match results for predicted fixtures that lack an outcome row
and upserts them into ``football.outcomes``.

The script is **prediction-driven**: it only ingests outcomes for
fixtures that already have at least one prediction row.  This keeps
the outcomes table focused on fixtures the system actually predicted.

Usage::

    python -m backend.football.scripts.ingest_outcomes

Exit codes
----------
- 0  — success (including "nothing to do")
- 1  — at least one fixture failed to ingest
"""

from __future__ import annotations

import asyncio
import logging
import sys

from sqlalchemy import select

from backend.cache import CacheClient
from backend.football._perf import _emit
from backend.football.data_provider import APIFootballClient
from backend.football.persistence import save_outcome
from backend.football.predictions.derivations import is_knockout_round
from backend.football.schemas import AFEvent, AFFixture
from backend.shared.async_singleflight import AsyncSingleflight
from backend.shared.db import get_db_session
from backend.shared.models import Outcome, Prediction
from backend.shared.settings import get_settings

logger = logging.getLogger(__name__)

# ── Status classification ────────────────────────────────────────────

# Completed with valid regulation-time score data.
_COMPLETED = frozenset({"FT", "AET", "PEN"})

# Abnormal termination — no meaningful score, skip with warning.
_SKIP_WARN = frozenset({"PST", "CANC", "ABD", "AWD", "WO"})


def _first_scorer_team(events: list[AFEvent]) -> str | None:
    """Return the name of the team that scored first, or None if no goals.

    Uses the earliest 'Goal' event by elapsed time. Own goals are not
    special-cased — the event's ``team`` is taken as-is (per EVAL-1's
    "first Goal event → team"); an own-goal opener is a rare edge case noted
    as a known limitation.
    """
    goals = [e for e in events if e.type == "Goal"]
    if not goals:
        return None
    goals.sort(key=lambda e: ((e.time.elapsed or 0), (e.time.extra or 0)))
    return goals[0].team.name


# ── Knockout advancer (EVAL-2) ───────────────────────────────────────


def _decided_by(fixture: AFFixture) -> str:
    """How a knockout tie was decided, from the score fields.

    penalty present → ``penalties`` (a pens match also carries an ET score,
    so penalty is checked FIRST); else a non-level ET score → ``extra_time``;
    else ``regulation``.
    """
    s = fixture.score
    if s.penalty.home is not None and s.penalty.away is not None:
        return "penalties"
    if (
        s.extratime.home is not None
        and s.extratime.away is not None
        and s.extratime.home != s.extratime.away
    ):
        return "extra_time"
    return "regulation"


def _knockout_advancer(fixture: AFFixture) -> tuple[str | None, str]:
    """Return ``(advancing_team_name, decided_by)`` for a knockout fixture.

    The advancer is resolved by a fallback chain (EVAL-2-PRE):
      1. ``teams.{home,away}.winner`` boolean — authoritative; it reflects
         the shootout / extra-time winner, not the 90-min scoreline.
      2. penalty score (higher advances) — for pens when winner is missing.
      3. 120-min cumulative = fulltime + extratime (higher advances).
      4. fulltime alone (higher advances).
    Returns ``(None, decided_by)`` when advancement can't be determined
    (all level, no penalty, no winner) — the caller emits a tripwire and
    leaves it null rather than guessing.
    """
    home = fixture.teams.home
    away = fixture.teams.away
    s = fixture.score
    decided_by = _decided_by(fixture)

    # 1. winner boolean (exactly one True).
    if home.winner is True and away.winner is not True:
        return home.name, decided_by
    if away.winner is True and home.winner is not True:
        return away.name, decided_by

    # 2. penalty shootout.
    if (
        s.penalty.home is not None
        and s.penalty.away is not None
        and s.penalty.home != s.penalty.away
    ):
        return (home.name if s.penalty.home > s.penalty.away else away.name), decided_by

    # 3. 120-min cumulative (regulation + extra time).
    cum_home = (s.fulltime.home or 0) + (s.extratime.home or 0)
    cum_away = (s.fulltime.away or 0) + (s.extratime.away or 0)
    if cum_home != cum_away:
        return (home.name if cum_home > cum_away else away.name), decided_by

    # 4. fulltime (regulation) margin.
    if (
        s.fulltime.home is not None
        and s.fulltime.away is not None
        and s.fulltime.home != s.fulltime.away
    ):
        return (home.name if s.fulltime.home > s.fulltime.away else away.name), decided_by

    # Undeterminable — do NOT guess.
    return None, decided_by


# ── Core logic ───────────────────────────────────────────────────────


async def run_ingest() -> dict:
    """Ingest missing outcomes.  Returns a counts dict.

    ``{"missing": int, "ingested": int, "skipped": int, "errors": int}``
    Idempotent: only fixtures with a prediction but no outcome row are
    fetched, so a re-run with nothing newly completed does no writes.
    """
    settings = get_settings()
    if not settings.api_football_key:
        logger.error("API_FOOTBALL_KEY not set in environment / .env")
        return 1

    # ── Phase 1: identify fixtures needing outcomes ──────────────

    async with get_db_session() as session:
        predicted_result = await session.execute(
            select(Prediction.fixture_id).distinct()
        )
        predicted_ids = set(predicted_result.scalars().all())

        outcome_result = await session.execute(
            select(Outcome.fixture_id)
        )
        existing_ids = set(outcome_result.scalars().all())

    missing_ids = sorted(predicted_ids - existing_ids)

    logger.info(
        "Predicted fixtures: %d | existing outcomes: %d | missing: %d",
        len(predicted_ids),
        len(existing_ids),
        len(missing_ids),
    )

    if not missing_ids:
        print(
            f"{len(predicted_ids)} fixtures with predictions "
            f"but no outcomes. Nothing to ingest."
        )
        return {"missing": 0, "ingested": 0, "skipped": 0, "errors": 0}

    print(
        f"{len(missing_ids)} fixtures with predictions "
        f"but no outcomes. Ingesting…"
    )

    # ── Phase 2: fetch & upsert each missing outcome ─────────────

    cache = CacheClient()
    sf = AsyncSingleflight()
    ingested = 0
    skipped = 0
    errors = 0

    async with APIFootballClient(
        settings.api_football_key, cache, sf
    ) as client:
        for fixture_id in missing_ids:
            try:
                fixture = await client.get_fixture(fixture_id)

                if fixture is None:
                    logger.warning(
                        "Fixture %d not found in API, skipping",
                        fixture_id,
                    )
                    skipped += 1
                    continue

                status = fixture.fixture.status.short

                # ── Skip abnormal statuses ──────────────────
                if status in _SKIP_WARN:
                    logger.warning(
                        "Fixture %d status=%s — no valid score, skipping",
                        fixture_id,
                        status,
                    )
                    skipped += 1
                    continue

                # ── Skip non-completed (still in play or not started) ──
                if status not in _COMPLETED:
                    logger.info(
                        "Fixture %d status=%s — not yet completed, skipping",
                        fixture_id,
                        status,
                    )
                    skipped += 1
                    continue

                # ── Extract regulation-time score ───────────
                # Use score.fulltime (90-min regulation), NOT
                # goals (which includes ET for AET/PEN matches).
                ft_home = fixture.score.fulltime.home
                ft_away = fixture.score.fulltime.away

                if ft_home is None or ft_away is None:
                    logger.warning(
                        "Fixture %d status=%s but null fulltime score, "
                        "skipping",
                        fixture_id,
                        status,
                    )
                    skipped += 1
                    continue

                ht_home = fixture.score.halftime.home
                ht_away = fixture.score.halftime.away

                # ── Knockout advancer (EVAL-2) ──────────────
                # Knockout fixtures grade against the team that ADVANCED, not
                # the 90-min result. Group fixtures skip this entirely
                # (advancer_team stays None → grading uses the 90-min W/D/L).
                advancer_team = None
                decided_by = None
                if is_knockout_round(fixture.league.round):
                    advancer_team, decided_by = _knockout_advancer(fixture)
                    if advancer_team is None:
                        # Couldn't tell who advanced — never guess; flag it.
                        _emit({
                            "event": "knockout_advancer_undetermined",
                            "fixture_id": fixture_id,
                        })

                # ── First scorer (best-effort) ──────────────
                # Events power first_to_score evaluation. A failure here must
                # not block saving the outcome — fall back to None.
                first_scorer_team = None
                try:
                    events = await client.get_events(fixture_id)
                    first_scorer_team = _first_scorer_team(events)
                except Exception:
                    logger.warning(
                        "Could not fetch events for fixture %d; "
                        "first_scorer_team=None",
                        fixture_id,
                    )

                # ── Upsert outcome ──────────────────────────
                async with get_db_session() as session:
                    await save_outcome(
                        session,
                        fixture_id=fixture_id,
                        home_team=fixture.teams.home.name,
                        away_team=fixture.teams.away.name,
                        ft_home=ft_home,
                        ft_away=ft_away,
                        ht_home=ht_home,
                        ht_away=ht_away,
                        first_scorer_team=first_scorer_team,
                        round=fixture.league.round,
                        advancer_team=advancer_team,
                        decided_by=decided_by,
                        kickoff_at=fixture.fixture.date,
                    )
                    await session.commit()

                ingested += 1
                logger.info(
                    "Ingested fixture %d: %s %d–%d %s (%s)",
                    fixture_id,
                    fixture.teams.home.name,
                    ft_home,
                    ft_away,
                    fixture.teams.away.name,
                    status,
                )

            except Exception:
                errors += 1
                logger.exception(
                    "Failed to ingest fixture %d", fixture_id
                )
                # Each fixture gets its own session, so a failure here
                # does not affect previously committed outcomes.
                continue

    # ── Summary ──────────────────────────────────────────────────

    print(
        f"\nIngestion complete: "
        f"{ingested} ingested, {skipped} skipped, {errors} errors"
    )

    return {
        "missing": len(missing_ids),
        "ingested": ingested,
        "skipped": skipped,
        "errors": errors,
    }


# ── Entry point ──────────────────────────────────────────────────────


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-5s %(name)s: %(message)s",
    )
    result = asyncio.run(run_ingest())
    sys.exit(1 if result["errors"] > 0 else 0)


if __name__ == "__main__":
    main()
