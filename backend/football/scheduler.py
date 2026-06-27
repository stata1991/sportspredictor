"""In-process pre-warm scheduler.

Fires ``_warm_fixtures_background`` once on startup, then every
``PREWARM_INTERVAL_SECONDS``.  The entire per-tick body — including
Sentry check-in calls — is inside one broad try/except so nothing
a tick does can kill the loop.  Only ``CancelledError`` exits.

Started by the app lifespan in ``main.py`` when
``PREWARM_SCHEDULER_ENABLED=true``.
"""

from __future__ import annotations

import asyncio
import time
import traceback
import uuid
from datetime import datetime, timedelta, timezone

import sentry_sdk
from sentry_sdk.crons import capture_checkin
from sentry_sdk.crons.consts import MonitorStatus

from backend.football._perf import _emit
from backend.football.routes import _warm_fixtures_background
from backend.shared.settings import get_settings

# Sentry Crons monitor slug.  The monitor is self-created via
# monitor_config on the first check-in.
_MONITOR_SLUG = "prewarm-scheduler"

# Monitor config passed with every check-in — upserts the monitor
# in Sentry so no manual UI creation is required.
_MONITOR_CONFIG = {
    "schedule": {"type": "interval", "value": 15, "unit": "minute"},
    "checkin_margin": 5,       # grace period (minutes) for missed check-ins
    # Sentry max_runtime is in MINUTES (was 120 with a "seconds" comment — a
    # hung warm would only flag after 120 MIN). Aligned with the per-cycle
    # asyncio.timeout (10 min) so a hung tick is flagged promptly.
    "max_runtime": 10,
    "failure_issue_threshold": 2,
    "recovery_threshold": 1,
}


# ── Per-cycle hang guard (EVAL-3) ────────────────────────────────────
# TRACK-4: a cycle's work (an uncapped DB await on a stalled Supabase
# pooler connection) hung the loop for 12.5h — the broad try/except below
# catches EXCEPTIONS but cannot catch a hang (an await that never returns),
# and there was no per-cycle timeout. These cap each cycle so a hang raises
# TimeoutError → is caught → the loop emits a timeout event and ticks again,
# instead of going silent forever. Aligned with the Sentry monitor
# max_runtime (minutes).
#
# NB: we use `async with asyncio.timeout(...)`, NOT `asyncio.wait_for(...)`.
# On Python 3.11, wait_for has a cancellation-loss race (bpo-42130): if the
# loop is cancelled (e.g. at shutdown) at the instant the inner coroutine
# resolves, wait_for returns the result and SWALLOWS the CancelledError, so
# the loop would never exit and shutdown would hang. asyncio.timeout (3.11+)
# propagates external cancellation cleanly while still raising TimeoutError
# on its own deadline — the correct primitive for a long-lived cancellable
# loop.
PREWARM_CYCLE_TIMEOUT_SECONDS = 600  # 10 min — a normal warm of ≤8 fixtures is ~2 min
EVAL_CYCLE_TIMEOUT_SECONDS = 600     # 10 min — ingest+compute is normally seconds


def _sentry_enabled() -> bool:
    """Check if Sentry is initialized (safe to call capture_*)."""
    return sentry_sdk.is_initialized()


# ── EVAL-4 Layer 2: abandon-on-timeout cycle guard ───────────────────
# EVAL-3 wrapped each cycle in `async with asyncio.timeout(...)`. TRACK-7
# proved that insufficient: the timeout cancels the CURRENT task at its await
# point, but the hung cycle's cleanup (get_db_session().__aexit__ → rollback/
# close on a black-holed Supabase socket) ALSO blocked, so the cancellation
# could not unwind — the loop parked pending forever, 16h silent, no event.
#
# Here a cycle runs as a CHILD task and we stop WAITING for it on timeout
# (asyncio.wait returns the pending set WITHOUT awaiting it). The loop's
# progress never depends on the hung task finishing — even an UNCANCELLABLE
# teardown can no longer park the loop. `asyncio.wait` (not `asyncio.wait_for`)
# is deliberate: wait_for has the bpo-42130 cancellation-loss race EVAL-3
# called out; asyncio.wait does not cancel-on-timeout and surfaces external
# (shutdown) cancellation cleanly.
WATCHDOG_TIMEOUT_SECONDS = 60  # the grading watchdog does ≤1 cached fetch + 1 query


async def _run_cycle(coro_factory, timeout_seconds: float):
    """Run one scheduler cycle, abandoning it if it blows the time budget.

    Returns the cycle's result on success; re-raises its exception; raises
    ``asyncio.TimeoutError`` if it exceeds ``timeout_seconds`` (the hung task
    is best-effort cancelled and then ORPHANED — never awaited).
    """
    task = asyncio.create_task(coro_factory())
    try:
        done, pending = await asyncio.wait({task}, timeout=timeout_seconds)
    except asyncio.CancelledError:
        task.cancel()  # shutdown: don't leak the child
        raise
    if task in pending:
        task.cancel()  # best-effort; we do NOT await the (maybe wedged) teardown
        raise asyncio.TimeoutError
    return task.result()


async def _drop_pooled_connections() -> None:
    """Force-drop pooled DB connections after a hung cycle so a parked /
    half-open connection cannot poison the next cycle. Self-bounded: a dispose
    that itself blocks must not re-hang the loop (keepalives cap it at ~60s;
    the timeout is a belt-and-braces second cap)."""
    try:
        from backend.shared.db import engine

        async with asyncio.timeout(10):
            await engine.dispose()
    except Exception:
        pass


# ── EVAL-4 Layer 3: cross-loop grading watchdog ──────────────────────
# Placed in the PREWARM loop, NOT the eval loop. TRACK-7 is decisive: the
# eval loop is the thing that dies, and the prewarm loop ran the full 16h it
# was dead. A watchdog inside the eval loop would have died WITH it and seen
# nothing. From the surviving prewarm context it observes the eval loop two
# independent, cause-agnostic ways — either signal is the alert all three
# prior grading freezes would have tripped regardless of their differing
# causes.
class _EvalHeartbeat:
    """Liveness beacon the eval loop stamps on every successful cycle and the
    prewarm-loop watchdog reads. Monotonic for math (immune to wall-clock
    jumps), wall for human-readable display in the alert."""

    def __init__(self) -> None:
        self._mono: float | None = None
        self._wall: datetime | None = None

    def record(self) -> None:
        self._mono = time.monotonic()
        self._wall = datetime.now(timezone.utc)

    @property
    def monotonic(self) -> float | None:
        return self._mono

    @property
    def wall(self) -> datetime | None:
        return self._wall


_eval_heartbeat = _EvalHeartbeat()


# Wall-clock minutes from kickoff to full time, by final status. Covers the
# 45+45 of play, the ~15-min halftime, and typical stoppage; AET/PEN add the
# extra-time period and the shootout. The API models no match-end timestamp
# (only kickoff date + status), so finish time is DERIVED. A ±10-min derivation
# error is immaterial against the 1h alarm threshold, and erring slightly LONG
# is deliberate: it can only shrink the measured lag, never inflate it — the
# opposite of the false positive TRACK-10 removes.
_FINISH_OFFSET_MINUTES: dict[str, int] = {
    "FT": 115,
    "AET": 150,
    "PEN": 165,
}
_DEFAULT_FINISH_OFFSET_MINUTES = 115


async def _grading_lag_seconds() -> tuple[float | None, dict | None]:
    """True grading delay: wall-clock seconds since the OLDEST finished-but-
    ungraded predicted fixture reached full time.

    Returns ``(lag_seconds, offender)``; ``lag_seconds`` is ``None`` when
    nothing is FT-but-ungraded (healthy / idle — there is no lag to report),
    in which case ``offender`` is ``None`` too.

    TRACK-10: the prior metric diffed KICKOFF timestamps
    (``newest_completed.kickoff − max(Outcome.kickoff_at)``), so a match graded
    one cycle late on a sparse slate reported the inter-match kickoff SPACING
    (hours) as "lag" instead of the true since-FT delay (~10 min) — a guaranteed
    false positive on every clustered/knockout night. This measures wall-clock
    time since the match actually FINISHED (kickoff + a per-status offset), so a
    match graded ~10 min after FT reports ~10 min regardless of how far its
    kickoff sits from the previously graded match.

    Universe = run_ingest's universe (predicted AND not yet graded): a completed
    fixture with no prediction can never be graded by ``run_ingest``, so
    counting it would be a permanent false lag of a different kind.
    """
    from sqlalchemy import select

    from backend.cache import CacheClient
    from backend.football.data_provider import APIFootballClient
    from backend.football.scripts.ingest_outcomes import _COMPLETED
    from backend.shared.async_singleflight import AsyncSingleflight
    from backend.shared.db import get_db_session
    from backend.shared.models import Outcome, Prediction

    settings = get_settings()
    now = datetime.now(timezone.utc)

    # The prewarm loop just fetched this list — no extra API cost.
    async with APIFootballClient(
        settings.api_football_key, CacheClient(), AsyncSingleflight()
    ) as client:
        fixtures = await client.get_fixtures()

    async with get_db_session() as session:
        predicted_ids = set(
            (
                await session.execute(select(Prediction.fixture_id).distinct())
            ).scalars().all()
        )
        graded_ids = set(
            (await session.execute(select(Outcome.fixture_id))).scalars().all()
        )

    oldest_finish: datetime | None = None
    offender: dict | None = None
    for fx in fixtures:
        status = fx.fixture.status.short
        if status not in _COMPLETED:
            continue
        fid = fx.fixture.id
        if fid not in predicted_ids or fid in graded_ids:
            continue

        offset = _FINISH_OFFSET_MINUTES.get(
            status, _DEFAULT_FINISH_OFFSET_MINUTES
        )
        finish = fx.fixture.date + timedelta(minutes=offset)
        # A just-FT match whose DERIVED finish is still in the future
        # contributes no lag yet — guards against the offset over-estimating
        # and producing a spurious negative/early lag.
        if finish > now:
            continue

        if oldest_finish is None or finish < oldest_finish:
            oldest_finish = finish
            offender = {
                "fixture_id": fid,
                "status": status,
                "kickoff": fx.fixture.date.isoformat(),
                "derived_finish": finish.isoformat(),
            }

    if oldest_finish is None:
        return None, None  # nothing FT-but-ungraded → no lag

    return (now - oldest_finish).total_seconds(), offender


async def _check_grading_liveness(*, eval_interval_seconds: int) -> None:
    """Observe the eval loop from the surviving prewarm context (EVAL-4 L3).

    Emits a Sentry signal + structured event on either of two checks. Never
    raises into the prewarm loop — the heartbeat half (cheap, no I/O) runs
    first and unconditionally, so an alert still fires even if the freshness
    half (which does I/O and could itself be wedged) blows up.
    """
    settings = get_settings()
    if not settings.eval_scheduler_enabled:
        return  # nothing to watch

    threshold = 2 * eval_interval_seconds

    # (a) HEARTBEAT — has the eval loop completed a cycle within 2× interval?
    last_mono = _eval_heartbeat.monotonic
    if last_mono is None or (time.monotonic() - last_mono) > threshold:
        secs = None if last_mono is None else round(time.monotonic() - last_mono)
        last_wall = _eval_heartbeat.wall
        _emit({
            "event": "eval_heartbeat_missed",
            "last_eval_run": last_wall.isoformat() if last_wall else None,
            "seconds_since_last": secs,
            "threshold_seconds": threshold,
        })
        if _sentry_enabled():
            try:
                sentry_sdk.capture_message(
                    "eval_heartbeat_missed: grading loop stalled", level="error"
                )
            except Exception:
                pass

    # (b) GRADING LAG — true wall-clock delay since the OLDEST finished-but-
    # ungraded match reached full time (TRACK-10). NOT a kickoff-to-kickoff gap:
    # a match graded ~10 min after FT reports ~10 min even when its kickoff sits
    # hours from the previously graded match (the sparse-slate false positive).
    try:
        lag, offender = await _grading_lag_seconds()
        if lag is not None and lag > threshold:
            _emit({
                "event": "grading_lag",
                "lag_minutes": round(lag / 60, 1),
                "oldest_ungraded": offender,
                "threshold_seconds": threshold,
            })
            if _sentry_enabled():
                try:
                    sentry_sdk.capture_message(
                        "grading_lag: graded corpus behind finished matches",
                        level="error",
                    )
                except Exception:
                    pass
    except Exception as exc:
        _emit({
            "event": "grading_watchdog_error",
            "phase": "freshness",
            "error": repr(exc),
        })


async def _scheduler_loop() -> None:
    """Run pre-warm ticks forever until cancelled.

    Fires immediately on first iteration (no initial sleep), then
    sleeps ``interval`` seconds between subsequent ticks.

    The entire per-tick body (check-in start → warm dispatch →
    check-in finish) is inside one broad try/except.  Each phase
    is tracked so errors are diagnosable.  Only CancelledError
    exits the loop.
    """
    settings = get_settings()
    interval = settings.prewarm_interval_seconds
    window_start_minutes = settings.prewarm_window_start_minutes
    window_end_minutes = settings.prewarm_window_end_minutes

    _emit({
        "event": "scheduler_started",
        "interval_seconds": interval,
        "window_start_minutes": window_start_minutes,
        "window_end_minutes": window_end_minutes,
    })

    try:
        while True:
            tick_id = str(uuid.uuid4())
            phase = "init"

            try:
                # ── Phase: checkin_start ──────────────────────────
                check_in_id = None
                if _sentry_enabled():
                    phase = "checkin_start"
                    check_in_id = capture_checkin(
                        monitor_slug=_MONITOR_SLUG,
                        status=MonitorStatus.IN_PROGRESS,
                        monitor_config=_MONITOR_CONFIG,
                    )

                # ── Phase: warm_dispatch ──────────────────────────
                phase = "warm_dispatch"
                now = datetime.now(timezone.utc)
                window_start = now + timedelta(minutes=window_start_minutes)
                window_end = now + timedelta(minutes=window_end_minutes)

                # Per-cycle guard (EVAL-4): a hung warm is ABANDONED (not just
                # cancelled) so the loop survives even if teardown wedges. A
                # silent prewarm hang means cold, slow match pages.
                await _run_cycle(
                    lambda: _warm_fixtures_background(
                        tick_id=tick_id,
                        window_start=window_start,
                        window_end=window_end,
                        dry_run=False,
                    ),
                    PREWARM_CYCLE_TIMEOUT_SECONDS,
                )

                # ── Phase: grading_watchdog (EVAL-4 L3) ───────────
                # Observe the EVAL loop from THIS loop, which survives an eval
                # death (TRACK-7). Abandon-guarded and try-wrapped: a watchdog
                # stall or error must never perturb the prewarm cycle.
                phase = "grading_watchdog"
                try:
                    await _run_cycle(
                        lambda: _check_grading_liveness(
                            eval_interval_seconds=settings.eval_interval_seconds
                        ),
                        WATCHDOG_TIMEOUT_SECONDS,
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    _emit({
                        "event": "grading_watchdog_error",
                        "phase": phase,
                        "error": repr(exc),
                    })

                # ── Phase: checkin_finish ─────────────────────────
                if _sentry_enabled() and check_in_id is not None:
                    phase = "checkin_finish"
                    capture_checkin(
                        monitor_slug=_MONITOR_SLUG,
                        check_in_id=check_in_id,
                        status=MonitorStatus.OK,
                        monitor_config=_MONITOR_CONFIG,
                    )

            except asyncio.CancelledError:
                raise  # Must propagate — this exits the loop

            except asyncio.TimeoutError:
                # Hung warm cycle — abandoned, flagged, and the loop ticks on.
                _emit({
                    "event": "prewarm_timeout",
                    "tick_id": tick_id,
                    "timeout_seconds": PREWARM_CYCLE_TIMEOUT_SECONDS,
                    "phase": phase,
                })
                # Drop pooled connections so a parked/half-open one (the likely
                # cause of the hang) can't poison the next cycle.
                await _drop_pooled_connections()
                if _sentry_enabled() and check_in_id is not None:
                    try:
                        capture_checkin(
                            monitor_slug=_MONITOR_SLUG,
                            check_in_id=check_in_id,
                            status=MonitorStatus.ERROR,
                            monitor_config=_MONITOR_CONFIG,
                        )
                    except Exception:
                        pass

            except Exception as exc:
                _emit({
                    "event": "scheduler_tick_error",
                    "tick_id": tick_id,
                    "error": repr(exc),
                    "phase": phase,
                })
                if _sentry_enabled():
                    try:
                        sentry_sdk.capture_exception(exc)
                    except Exception:
                        pass  # Cannot let Sentry reporting kill the loop

                # Try to mark the check-in as error (best effort)
                if _sentry_enabled() and check_in_id is not None:
                    try:
                        capture_checkin(
                            monitor_slug=_MONITOR_SLUG,
                            check_in_id=check_in_id,
                            status=MonitorStatus.ERROR,
                            monitor_config=_MONITOR_CONFIG,
                        )
                    except Exception:
                        pass

            await asyncio.sleep(interval)

    except asyncio.CancelledError:
        _emit({"event": "scheduler_stopped"})
        raise


async def start_scheduler() -> asyncio.Task | None:
    """Create the scheduler task if the flag is enabled.

    Returns the task (for cancellation on shutdown) or None if
    the scheduler is disabled.
    """
    settings = get_settings()
    if not settings.prewarm_scheduler_enabled:
        return None
    return asyncio.create_task(_scheduler_loop())


# ── Evaluation scheduler (Track Record rollups) ───────────────────────

_EVAL_MONITOR_SLUG = "eval-scheduler"

_EVAL_MONITOR_CONFIG = {
    "schedule": {"type": "interval", "value": 30, "unit": "minute"},
    "checkin_margin": 5,
    "max_runtime": 10,  # minutes — ingest + compute is quick
    "failure_issue_threshold": 2,
    "recovery_threshold": 1,
}


async def run_evaluation() -> dict:
    """Run the evaluation pipeline once: ingest outcomes, then recompute the
    rollups (replace-in-place).  Returns ``{"ingested": N, "rollups_written": M}``.

    Cheap when nothing new completed — ingest only fetches fixtures that have
    a prediction but no outcome row, and compute replaces the small grid.
    """
    from backend.football.scripts.compute_accuracy import run_compute
    from backend.football.scripts.ingest_outcomes import run_ingest

    ingest_result = await run_ingest()
    compute_result = await run_compute()
    return {
        "ingested": ingest_result["ingested"],
        "rollups_written": compute_result["rollups_written"],
    }


async def _eval_scheduler_loop() -> None:
    """Run evaluation ticks forever until cancelled.

    Same hardened pattern as ``_scheduler_loop``: the whole per-tick body
    (Sentry check-in → ingest+compute → check-in finish) is inside one broad
    try/except so nothing a tick does can kill the loop.  Only CancelledError
    exits.  Fires immediately on first iteration, then every ``interval``.
    """
    settings = get_settings()
    interval = settings.eval_interval_seconds

    _emit({"event": "eval_scheduler_started", "interval_seconds": interval})
    # Establish a boot baseline so the cross-loop watchdog does not false-trip
    # before the first cycle completes (the loop fires immediately, so a real
    # success stamps within seconds; this covers the gap in between).
    _eval_heartbeat.record()

    try:
        while True:
            phase = "init"
            try:
                check_in_id = None
                if _sentry_enabled():
                    phase = "checkin_start"
                    check_in_id = capture_checkin(
                        monitor_slug=_EVAL_MONITOR_SLUG,
                        status=MonitorStatus.IN_PROGRESS,
                        monitor_config=_EVAL_MONITOR_CONFIG,
                    )

                phase = "eval_run"
                # Per-cycle guard (EVAL-4): a hung run_evaluation is ABANDONED
                # — not merely cancelled — so the loop survives even when the
                # cycle's teardown wedges on a dead socket (TRACK-7), instead
                # of parking pending forever.
                counts = await _run_cycle(
                    run_evaluation, EVAL_CYCLE_TIMEOUT_SECONDS
                )
                _emit({
                    "event": "eval_run",
                    "ingested": counts["ingested"],
                    "rollups_written": counts["rollups_written"],
                })
                # Stamp the liveness beacon ONLY on a fully successful cycle —
                # this is what the cross-loop watchdog reads.
                _eval_heartbeat.record()

                if _sentry_enabled() and check_in_id is not None:
                    phase = "checkin_finish"
                    capture_checkin(
                        monitor_slug=_EVAL_MONITOR_SLUG,
                        check_in_id=check_in_id,
                        status=MonitorStatus.OK,
                        monitor_config=_EVAL_MONITOR_CONFIG,
                    )

            except asyncio.CancelledError:
                raise

            except asyncio.TimeoutError:
                # THE TRACK-4 failure mode, now recoverable: a cycle exceeded
                # the timeout (assumed hung) and was cancelled. Emit a
                # distinct event, mark the check-in a definitive failure (so
                # the monitor alerts instead of leaving it IN_PROGRESS), then
                # fall through to sleep + tick again.
                _emit({
                    "event": "eval_run_timeout",
                    "timeout_seconds": EVAL_CYCLE_TIMEOUT_SECONDS,
                    "phase": phase,
                })
                # Drop pooled connections so a parked/half-open one (the likely
                # cause of the hang) can't poison the next cycle.
                await _drop_pooled_connections()
                if _sentry_enabled() and check_in_id is not None:
                    try:
                        capture_checkin(
                            monitor_slug=_EVAL_MONITOR_SLUG,
                            check_in_id=check_in_id,
                            status=MonitorStatus.ERROR,
                            monitor_config=_EVAL_MONITOR_CONFIG,
                        )
                    except Exception:
                        pass

            except Exception as exc:
                _emit({
                    "event": "eval_scheduler_tick_error",
                    "error": repr(exc),
                    "phase": phase,
                })
                if _sentry_enabled():
                    try:
                        sentry_sdk.capture_exception(exc)
                    except Exception:
                        pass
                if _sentry_enabled() and check_in_id is not None:
                    try:
                        capture_checkin(
                            monitor_slug=_EVAL_MONITOR_SLUG,
                            check_in_id=check_in_id,
                            status=MonitorStatus.ERROR,
                            monitor_config=_EVAL_MONITOR_CONFIG,
                        )
                    except Exception:
                        pass

            await asyncio.sleep(interval)

    except asyncio.CancelledError:
        _emit({"event": "eval_scheduler_stopped"})
        raise


async def start_eval_scheduler() -> asyncio.Task | None:
    """Create the evaluation scheduler task if EVAL_SCHEDULER_ENABLED."""
    settings = get_settings()
    if not settings.eval_scheduler_enabled:
        return None
    return asyncio.create_task(_eval_scheduler_loop())
