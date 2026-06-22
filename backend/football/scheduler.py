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

                # Per-cycle timeout (EVAL-3): same hang guard as the eval loop
                # — a hung warm is cancelled so the loop survives and ticks
                # again. A silent prewarm hang means cold, slow match pages.
                async with asyncio.timeout(PREWARM_CYCLE_TIMEOUT_SECONDS):
                    await _warm_fixtures_background(
                        tick_id=tick_id,
                        window_start=window_start,
                        window_end=window_end,
                        dry_run=False,
                    )

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
                # Hung warm cycle — cancelled, flagged, and the loop ticks on.
                _emit({
                    "event": "prewarm_timeout",
                    "tick_id": tick_id,
                    "timeout_seconds": PREWARM_CYCLE_TIMEOUT_SECONDS,
                    "phase": phase,
                })
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
                # Per-cycle timeout (EVAL-3): a hung run_evaluation is
                # cancelled so the loop survives and ticks again instead of
                # going silent forever (TRACK-4).
                async with asyncio.timeout(EVAL_CYCLE_TIMEOUT_SECONDS):
                    counts = await run_evaluation()
                _emit({
                    "event": "eval_run",
                    "ingested": counts["ingested"],
                    "rollups_written": counts["rollups_written"],
                })

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
