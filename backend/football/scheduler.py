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
    "max_runtime": 120,        # seconds — a tick warming 4 fixtures takes ~2 min
    "failure_issue_threshold": 2,
    "recovery_threshold": 1,
}


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
