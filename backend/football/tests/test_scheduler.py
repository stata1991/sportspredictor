"""Tests for the in-process pre-warm scheduler (pre-warm-3 / pre-warm-4 / pre-warm-4.1).

Verifies:
- Flag OFF → no task created
- Flag ON → task created, fires promptly, then on interval
- A failing tick → error emitted with repr(exc) + phase, loop survives
- Sentry capture_exception called on error when enabled; not called when disabled
- capture_checkin failure cannot kill the loop (check-in start and finish paths)
- monitor_config passed for self-creating upsert
- Graceful shutdown → scheduler_stopped emitted
- Window is read from settings (not hardcoded)
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch, call

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

        assert mock_warm.call_count >= 2

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
        1. Emit scheduler_tick_error with repr(exc) and phase=warm_dispatch
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
        assert "RuntimeError('API-Football exploded')" in error_events[0]["error"]
        assert error_events[0]["phase"] == "warm_dispatch"

    @patch("backend.football.scheduler.sentry_sdk")
    @patch("backend.football.scheduler.capture_checkin")
    @patch("backend.football.scheduler._sentry_enabled", return_value=True)
    @patch("backend.football.scheduler.get_settings")
    async def test_sentry_capture_called_when_enabled(
        self, mock_get_settings, _mock_sentry_enabled, mock_checkin,
        mock_sentry_sdk, capsys
    ):
        """When Sentry is enabled, capture_exception is called on tick failure."""
        mock_get_settings.return_value = _mock_settings(
            prewarm_interval_seconds=3600,
        )
        mock_checkin.return_value = "check-in-id"

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
    @patch("backend.football.scheduler.capture_checkin")
    @patch("backend.football.scheduler._sentry_enabled", return_value=False)
    @patch("backend.football.scheduler._warm_fixtures_background", new_callable=AsyncMock)
    @patch("backend.football.scheduler.get_settings")
    async def test_sentry_not_called_when_disabled(
        self, mock_get_settings, mock_warm, _mock_sentry_enabled,
        mock_checkin, mock_sentry_sdk, capsys
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
        mock_checkin.assert_not_called()


# ── Check-in failure cannot kill the loop ────────────────────────────


class TestCheckinFailureSurvival:
    @patch("backend.football.scheduler._warm_fixtures_background", new_callable=AsyncMock)
    @patch("backend.football.scheduler._sentry_enabled", return_value=True)
    @patch("backend.football.scheduler.get_settings")
    async def test_checkin_start_failure_does_not_kill_loop(
        self, mock_get_settings, _mock_sentry, mock_warm, capsys
    ):
        """capture_checkin raising on the start call must not kill the loop.
        The tick should emit scheduler_tick_error with phase=checkin_start
        and continue to the next tick.
        """
        mock_get_settings.return_value = _mock_settings(
            prewarm_interval_seconds=0,
        )

        call_count = 0

        def flaky_checkin(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("Sentry API unreachable")
            return "check-in-id"

        with patch(
            "backend.football.scheduler.capture_checkin",
            side_effect=flaky_checkin,
        ), patch("backend.football.scheduler.sentry_sdk"):
            from backend.football.scheduler import start_scheduler

            task = await start_scheduler()

            for _ in range(20):
                await asyncio.sleep(0)

            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        # The warm function was called at least once (tick 2 succeeded)
        assert mock_warm.call_count >= 1

        captured = capsys.readouterr()
        lines = [l for l in captured.out.strip().split("\n") if l]
        events = [json.loads(l) for l in lines]
        error_events = [
            e for e in events if e.get("event") == "scheduler_tick_error"
        ]
        assert len(error_events) >= 1
        assert error_events[0]["phase"] == "checkin_start"
        assert "ConnectionError" in error_events[0]["error"]

    @patch("backend.football.scheduler._sentry_enabled", return_value=True)
    @patch("backend.football.scheduler.get_settings")
    async def test_checkin_finish_failure_does_not_kill_loop(
        self, mock_get_settings, _mock_sentry, capsys
    ):
        """capture_checkin raising on the finish call must not kill the loop."""
        mock_get_settings.return_value = _mock_settings(
            prewarm_interval_seconds=0,
        )

        checkin_call_count = 0

        def flaky_finish_checkin(*args, **kwargs):
            nonlocal checkin_call_count
            checkin_call_count += 1
            status = kwargs.get("status")
            # Import locally to avoid issues
            from sentry_sdk.crons.consts import MonitorStatus
            if status == MonitorStatus.IN_PROGRESS:
                return "check-in-id"
            if status == MonitorStatus.OK and checkin_call_count <= 3:
                raise ConnectionError("Sentry finish failed")
            return "check-in-id"

        warm_count = 0

        async def counting_warm(**kwargs):
            nonlocal warm_count
            warm_count += 1

        with patch(
            "backend.football.scheduler.capture_checkin",
            side_effect=flaky_finish_checkin,
        ), patch(
            "backend.football.scheduler._warm_fixtures_background",
            side_effect=counting_warm,
        ), patch("backend.football.scheduler.sentry_sdk"):
            from backend.football.scheduler import start_scheduler

            task = await start_scheduler()

            for _ in range(20):
                await asyncio.sleep(0)

            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        # Multiple ticks ran despite finish failures
        assert warm_count >= 2

        captured = capsys.readouterr()
        lines = [l for l in captured.out.strip().split("\n") if l]
        events = [json.loads(l) for l in lines]
        error_events = [
            e for e in events if e.get("event") == "scheduler_tick_error"
        ]
        assert len(error_events) >= 1
        assert error_events[0]["phase"] == "checkin_finish"


# ── Monitor config passed for upsert ────────────────────────────────


class TestMonitorConfig:
    @patch("backend.football.scheduler._warm_fixtures_background", new_callable=AsyncMock)
    @patch("backend.football.scheduler._sentry_enabled", return_value=True)
    @patch("backend.football.scheduler.get_settings")
    async def test_monitor_config_passed_to_checkin(
        self, mock_get_settings, _mock_sentry, mock_warm, capsys
    ):
        """capture_checkin must receive monitor_config for self-creating upsert."""
        mock_get_settings.return_value = _mock_settings(
            prewarm_interval_seconds=3600,
        )

        checkin_calls = []

        def recording_checkin(*args, **kwargs):
            checkin_calls.append(kwargs)
            return "check-in-id"

        with patch(
            "backend.football.scheduler.capture_checkin",
            side_effect=recording_checkin,
        ), patch("backend.football.scheduler.sentry_sdk"):
            from backend.football.scheduler import start_scheduler

            task = await start_scheduler()

            for _ in range(5):
                await asyncio.sleep(0)

            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        # At least 2 check-in calls: IN_PROGRESS + OK
        assert len(checkin_calls) >= 2

        # Both calls should have monitor_config
        for c in checkin_calls:
            assert "monitor_config" in c
            config = c["monitor_config"]
            assert config["schedule"]["type"] == "interval"
            assert config["schedule"]["value"] == 15
            assert config["schedule"]["unit"] == "minute"
            assert config["checkin_margin"] == 5
            assert config["max_runtime"] == 120


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

        assert mock_warm.call_count >= 1
        call_kwargs = mock_warm.call_args[1]
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        ws = call_kwargs["window_start"]
        we = call_kwargs["window_end"]
        delta_start = (ws - now).total_seconds()
        delta_end = (we - now).total_seconds()
        assert 3500 < delta_start < 3700, f"Expected ~3600s, got {delta_start}"
        assert 7100 < delta_end < 7300, f"Expected ~7200s, got {delta_end}"
