"""Tests for the in-process pre-warm scheduler (pre-warm-3 / pre-warm-4).

Verifies:
- Flag OFF → no task created
- Flag ON → task created, fires promptly, then on interval
- A failing tick → error emitted with repr(exc), loop survives, next tick fires
- Graceful shutdown → scheduler_stopped emitted, task cancelled cleanly
- Window is read from settings (not hardcoded)
- Sentry capture_exception called on error when enabled; not called when disabled
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _mock_settings(**overrides):
    """Build a settings mock with all scheduler fields populated."""
    defaults = {
        "prewarm_scheduler_enabled": True,
        "prewarm_interval_seconds": 0,
        "prewarm_window_start_minutes": 90,
        "prewarm_window_end_minutes": 150,
    }
    defaults.update(overrides)
    return MagicMock(**defaults)


# ── Flag OFF: no task created ────────────────────────────────────────


class TestSchedulerFlagOff:
    @patch("backend.football.scheduler.get_settings")
    async def test_no_task_when_disabled(self, mock_get_settings):
        mock_get_settings.return_value = _mock_settings(
            prewarm_scheduler_enabled=False,
        )
        from backend.football.scheduler import start_scheduler

        task = await start_scheduler()
        assert task is None


# ── Flag ON: fires promptly + interval ───────────────────────────────


class TestSchedulerFlagOn:
    @patch("backend.football.scheduler._sentry_enabled", return_value=False)
    @patch("backend.football.scheduler._warm_fixtures_background", new_callable=AsyncMock)
    @patch("backend.football.scheduler.get_settings")
    async def test_fires_promptly_and_on_interval(
        self, mock_get_settings, mock_warm, _mock_sentry, capsys
    ):
        """With a very short interval, the scheduler fires at least twice."""
        mock_get_settings.return_value = _mock_settings(
            prewarm_interval_seconds=0,
        )

        from backend.football.scheduler import start_scheduler

        task = await start_scheduler()
        assert task is not None

        for _ in range(20):
            await asyncio.sleep(0)

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        assert mock_warm.call_count >= 2, (
            f"Expected ≥2 ticks, got {mock_warm.call_count}"
        )

        captured = capsys.readouterr()
        lines = [l for l in captured.out.strip().split("\n") if l]
        events = [json.loads(l) for l in lines]
        started_events = [e for e in events if e.get("event") == "scheduler_started"]
        assert len(started_events) == 1
        assert started_events[0]["interval_seconds"] == 0


# ── Failing tick: error with repr(exc), loop survives ────────────────


class TestSchedulerTickFailure:
    @patch("backend.football.scheduler._sentry_enabled", return_value=False)
    @patch("backend.football.scheduler.get_settings")
    async def test_failing_tick_carries_repr_and_survives(
        self, mock_get_settings, _mock_sentry, capsys
    ):
        """A tick whose warm call raises must:
        1. Emit scheduler_tick_error with repr(exc) (not a generic string)
        2. Continue to the next tick (loop survives)
        """
        mock_get_settings.return_value = _mock_settings(
            prewarm_interval_seconds=0,
        )

        call_count = 0

        async def flaky_warm(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("API-Football exploded")

        with patch(
            "backend.football.scheduler._warm_fixtures_background",
            side_effect=flaky_warm,
        ):
            from backend.football.scheduler import start_scheduler

            task = await start_scheduler()

            for _ in range(20):
                await asyncio.sleep(0)

            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        assert call_count >= 2

        captured = capsys.readouterr()
        lines = [l for l in captured.out.strip().split("\n") if l]
        events = [json.loads(l) for l in lines]
        error_events = [
            e for e in events if e.get("event") == "scheduler_tick_error"
        ]
        assert len(error_events) >= 1
        # Must carry repr(exc), not a generic string
        assert "RuntimeError('API-Football exploded')" in error_events[0]["error"]
        assert error_events[0]["phase"] == "warm_dispatch"

    @patch("backend.football.scheduler.sentry_sdk")
    @patch("backend.football.scheduler._sentry_enabled", return_value=True)
    @patch("backend.football.scheduler.get_settings")
    async def test_sentry_capture_called_when_enabled(
        self, mock_get_settings, _mock_sentry_enabled, mock_sentry_sdk, capsys
    ):
        """When Sentry is enabled, capture_exception must be called on tick failure."""
        mock_get_settings.return_value = _mock_settings(
            prewarm_interval_seconds=3600,
        )
        mock_sentry_sdk.crons.api.capture_checkin.return_value = "check-in-id"

        async def fail_warm(**kwargs):
            raise ValueError("db connection lost")

        with patch(
            "backend.football.scheduler._warm_fixtures_background",
            side_effect=fail_warm,
        ):
            from backend.football.scheduler import start_scheduler

            task = await start_scheduler()

            for _ in range(5):
                await asyncio.sleep(0)

            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        mock_sentry_sdk.capture_exception.assert_called_once()
        exc_arg = mock_sentry_sdk.capture_exception.call_args[0][0]
        assert isinstance(exc_arg, ValueError)
        assert "db connection lost" in str(exc_arg)

    @patch("backend.football.scheduler.sentry_sdk")
    @patch("backend.football.scheduler._sentry_enabled", return_value=False)
    @patch("backend.football.scheduler._warm_fixtures_background", new_callable=AsyncMock)
    @patch("backend.football.scheduler.get_settings")
    async def test_sentry_not_called_when_disabled(
        self, mock_get_settings, mock_warm, _mock_sentry_enabled, mock_sentry_sdk, capsys
    ):
        """When Sentry is disabled, no Sentry calls are made."""
        mock_get_settings.return_value = _mock_settings(
            prewarm_interval_seconds=3600,
        )

        from backend.football.scheduler import start_scheduler

        task = await start_scheduler()

        for _ in range(5):
            await asyncio.sleep(0)

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        mock_sentry_sdk.capture_exception.assert_not_called()
        mock_sentry_sdk.crons.api.capture_checkin.assert_not_called()


# ── Graceful shutdown: scheduler_stopped emitted ─────────────────────


class TestSchedulerShutdown:
    @patch("backend.football.scheduler._sentry_enabled", return_value=False)
    @patch("backend.football.scheduler._warm_fixtures_background", new_callable=AsyncMock)
    @patch("backend.football.scheduler.get_settings")
    async def test_emits_scheduler_stopped_on_cancellation(
        self, mock_get_settings, mock_warm, _mock_sentry, capsys
    ):
        """Cancelling the task emits scheduler_stopped."""
        mock_get_settings.return_value = _mock_settings(
            prewarm_interval_seconds=3600,
        )

        from backend.football.scheduler import start_scheduler

        task = await start_scheduler()
        assert task is not None

        for _ in range(5):
            await asyncio.sleep(0)

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        assert task.done()

        captured = capsys.readouterr()
        lines = [l for l in captured.out.strip().split("\n") if l]
        events = [json.loads(l) for l in lines]
        stopped_events = [e for e in events if e.get("event") == "scheduler_stopped"]
        assert len(stopped_events) == 1


# ── Window from settings ─────────────────────────────────────────────


class TestSchedulerWindowConfig:
    @patch("backend.football.scheduler._sentry_enabled", return_value=False)
    @patch("backend.football.scheduler._warm_fixtures_background", new_callable=AsyncMock)
    @patch("backend.football.scheduler.get_settings")
    async def test_window_from_settings(
        self, mock_get_settings, mock_warm, _mock_sentry, capsys
    ):
        """Loop reads window_start/end minutes from settings."""
        mock_get_settings.return_value = _mock_settings(
            prewarm_interval_seconds=3600,
            prewarm_window_start_minutes=60,
            prewarm_window_end_minutes=120,
        )

        from backend.football.scheduler import start_scheduler

        task = await start_scheduler()

        for _ in range(5):
            await asyncio.sleep(0)

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # Check the call to _warm_fixtures_background
        assert mock_warm.call_count >= 1
        call_kwargs = mock_warm.call_args[1]
        # window_start should be ~60 min from now, window_end ~120 min from now
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        ws = call_kwargs["window_start"]
        we = call_kwargs["window_end"]
        # window_start should be roughly 60 min from now (allow 5s tolerance)
        delta_start = (ws - now).total_seconds()
        delta_end = (we - now).total_seconds()
        assert 3500 < delta_start < 3700, f"Expected ~3600s, got {delta_start}"
        assert 7100 < delta_end < 7300, f"Expected ~7200s, got {delta_end}"
