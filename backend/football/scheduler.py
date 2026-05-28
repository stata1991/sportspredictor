"""In-process pre-warm scheduler.

Fires ``_warm_fixtures_background`` once on startup, then every
``PREWARM_INTERVAL_SECONDS``.  Each tick is wrapped in try/except so
a single failure can never kill the loop.

Started by the app lifespan in ``main.py`` when
``PREWARM_SCHEDULER_ENABLED=true``.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import sentry_sdk

from backend.football._perf import _emit
from backend.football.routes import _warm_fixtures_background
from backend.shared.settings import get_settings

# Sentry Crons monitor slug.  Must match the monitor configured in
# Sentry UI (schedule: every 15 min, max runtime: 120s, grace: 5 min).
_MONITOR_SLUG = "prewarm-scheduler"


def _sentry_enabled() -> bool:
    """Check if Sentry is initialized (safe to call capture_*)."""
    return sentry_sdk.is_initialized()


async def _scheduler_loop() -> None:
    """Run pre-warm ticks forever until cancelled.

    Fires immediately on first iteration (no initial sleep), then
    sleeps ``interval`` seconds between subsequent ticks.
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
            now = datetime.now(timezone.utc)
            window_start = now + timedelta(minutes=window_start_minutes)
            window_end = now + timedelta(minutes=window_end_minutes)

            # Sentry Cron check-in: start
            check_in_id = None
            if _sentry_enabled():
                check_in_id = sentry_sdk.crons.api.capture_checkin(
                    monitor_slug=_MONITOR_SLUG,
                    status=sentry_sdk.crons.consts.MonitorStatus.IN_PROGRESS,
                )

            tick_ok = True
            try:
                await _warm_fixtures_background(
                    tick_id=tick_id,
                    window_start=window_start,
                    window_end=window_end,
                    dry_run=False,
                )
            except Exception as exc:
                tick_ok = False
                _emit({
                    "event": "scheduler_tick_error",
                    "tick_id": tick_id,
                    "error": repr(exc),
                    "phase": "warm_dispatch",
                })
                if _sentry_enabled():
                    sentry_sdk.capture_exception(exc)

            # Sentry Cron check-in: finish
            if _sentry_enabled() and check_in_id is not None:
                sentry_sdk.crons.api.capture_checkin(
                    monitor_slug=_MONITOR_SLUG,
                    check_in_id=check_in_id,
                    status=(
                        sentry_sdk.crons.consts.MonitorStatus.OK
                        if tick_ok
                        else sentry_sdk.crons.consts.MonitorStatus.ERROR
                    ),
                )

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
