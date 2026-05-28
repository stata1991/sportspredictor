"""Tests for the in-process pre-warm scheduler (pre-warm-3).

Verifies:
- Flag OFF → no task created
- Flag ON → task created, fires promptly, then on interval
- A failing tick → error emitted, loop survives, next tick fires
- Graceful shutdown → task cancelled cleanly, no warnings
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── Flag OFF: no task created ────────────────────────────────────────


class TestSchedulerFlagOff:
    @patch("backend.football.scheduler.get_settings")
    async def test_no_task_when_disabled(self, mock_settings):
        mock_settings.return_value = MagicMock(
            prewarm_scheduler_enabled=False,
            prewarm_interval_seconds=900,
        )
        from backend.football.scheduler import start_scheduler

        task = await start_scheduler()
        assert task is None


# ── Flag ON: fires promptly + interval ───────────────────────────────


class TestSchedulerFlagOn:
    @patch("backend.football.scheduler._warm_fixtures_background", new_callable=AsyncMock)
    @patch("backend.football.scheduler.get_settings")
    async def test_fires_promptly_and_on_interval(
        self, mock_settings, mock_warm, capsys
    ):
        """With a very short interval, the scheduler fires at least twice."""
        mock_settings.return_value = MagicMock(
            prewarm_scheduler_enabled=True,
            prewarm_interval_seconds=0,  # fire as fast as possible
        )

        from backend.football.scheduler import start_scheduler

        task = await start_scheduler()
        assert task is not None

        # Let the event loop run for a bit so multiple ticks fire.
        # asyncio.sleep(0) yields control; we do it several times to
        # allow the loop to iterate.
        for _ in range(20):
            await asyncio.sleep(0)

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # At least 2 ticks should have fired
        assert mock_warm.call_count >= 2, (
            f"Expected ≥2 ticks, got {mock_warm.call_count}"
        )

        # Check scheduler_started event was emitted
        captured = capsys.readouterr()
        lines = [l for l in captured.out.strip().split("\n") if l]
        events = [json.loads(l) for l in lines]
        started_events = [e for e in events if e.get("event") == "scheduler_started"]
        assert len(started_events) == 1
        assert started_events[0]["interval_seconds"] == 0


# ── Failing tick: error emitted, loop survives ───────────────────────


class TestSchedulerTickFailure:
    @patch("backend.football.scheduler.get_settings")
    async def test_failing_tick_does_not_kill_loop(
        self, mock_settings, capsys
    ):
        """A tick whose warm call raises must not stop the scheduler.
        The loop must emit a scheduler_tick_error and continue to the
        next tick.
        """
        mock_settings.return_value = MagicMock(
            prewarm_scheduler_enabled=True,
            prewarm_interval_seconds=0,
        )

        call_count = 0

        async def flaky_warm(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("API-Football exploded")
            # Subsequent calls succeed silently

        with patch(
            "backend.football.scheduler._warm_fixtures_background",
            side_effect=flaky_warm,
        ):
            from backend.football.scheduler import start_scheduler

            task = await start_scheduler()

            # Let the loop run enough to get past the first (failing) tick
            # and fire a second (succeeding) tick.
            for _ in range(20):
                await asyncio.sleep(0)

            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        # The warm function was called at least twice: the failing tick
        # plus at least one more successful tick.
        assert call_count >= 2, (
            f"Expected ≥2 calls (first fails, second succeeds), got {call_count}"
        )

        # An error event was emitted for the failing tick
        captured = capsys.readouterr()
        lines = [l for l in captured.out.strip().split("\n") if l]
        events = [json.loads(l) for l in lines]
        error_events = [
            e for e in events if e.get("event") == "scheduler_tick_error"
        ]
        assert len(error_events) >= 1
        assert "tick failed" in error_events[0]["error"]


# ── Graceful shutdown ────────────────────────────────────────────────


class TestSchedulerShutdown:
    @patch("backend.football.scheduler._warm_fixtures_background", new_callable=AsyncMock)
    @patch("backend.football.scheduler.get_settings")
    async def test_graceful_cancellation(self, mock_settings, mock_warm):
        """Cancelling the task should not raise or produce warnings."""
        mock_settings.return_value = MagicMock(
            prewarm_scheduler_enabled=True,
            prewarm_interval_seconds=3600,  # long interval — won't fire a second tick
        )

        from backend.football.scheduler import start_scheduler

        task = await start_scheduler()
        assert task is not None

        # Let the first tick fire
        for _ in range(5):
            await asyncio.sleep(0)

        # Cancel (simulating app shutdown)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # Task is done and cancelled — no "task was destroyed" warning
        assert task.done()
        assert task.cancelled()
