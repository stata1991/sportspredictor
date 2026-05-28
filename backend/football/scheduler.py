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

from backend.football._perf import _emit
from backend.football.routes import _warm_fixtures_background
from backend.shared.settings import get_settings


async def _scheduler_loop() -> None:
    """Run pre-warm ticks forever until cancelled.

    Fires immediately on first iteration (no initial sleep), then
    sleeps ``interval`` seconds between subsequent ticks.
    """
    settings = get_settings()
    interval = settings.prewarm_interval_seconds

    _emit({
        "event": "scheduler_started",
        "interval_seconds": interval,
    })

    while True:
        tick_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        window_start = now + timedelta(minutes=90)
        window_end = now + timedelta(minutes=150)

        try:
            await _warm_fixtures_background(
                tick_id=tick_id,
                window_start=window_start,
                window_end=window_end,
                dry_run=False,
            )
        except Exception:
            _emit({
                "event": "scheduler_tick_error",
                "tick_id": tick_id,
                "error": "tick failed — see logs",
            })

        await asyncio.sleep(interval)


async def start_scheduler() -> asyncio.Task | None:
    """Create the scheduler task if the flag is enabled.

    Returns the task (for cancellation on shutdown) or None if
    the scheduler is disabled.
    """
    settings = get_settings()
    if not settings.prewarm_scheduler_enabled:
        return None
    return asyncio.create_task(_scheduler_loop())
