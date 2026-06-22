"""Tests for the in-process evaluation scheduler (EVAL-1).

- Flag OFF → no task created
- Flag ON → task created, fires promptly + on interval, emits eval_run
- run_evaluation orchestrates ingest → compute and returns combined counts
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _mock_settings(**overrides):
    defaults = {
        "eval_scheduler_enabled": True,
        "eval_interval_seconds": 0,
    }
    defaults.update(overrides)
    return MagicMock(**defaults)


# ── Flag gating ──────────────────────────────────────────────────────


class TestEvalSchedulerFlag:
    @patch("backend.football.scheduler.get_settings")
    async def test_no_task_when_disabled(self, mock_get_settings):
        mock_get_settings.return_value = _mock_settings(
            eval_scheduler_enabled=False
        )
        from backend.football.scheduler import start_eval_scheduler

        task = await start_eval_scheduler()
        assert task is None

    @patch("backend.football.scheduler.run_evaluation", new_callable=AsyncMock)
    @patch("backend.football.scheduler._sentry_enabled", return_value=False)
    @patch("backend.football.scheduler.get_settings")
    async def test_task_created_when_enabled(
        self, mock_get_settings, _mock_sentry, mock_run_eval
    ):
        mock_get_settings.return_value = _mock_settings()
        mock_run_eval.return_value = {"ingested": 0, "rollups_written": 0}
        from backend.football.scheduler import start_eval_scheduler

        task = await start_eval_scheduler()
        assert task is not None
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


# ── Loop fires + emits eval_run ──────────────────────────────────────


class TestEvalLoopFires:
    @patch("backend.football.scheduler.run_evaluation", new_callable=AsyncMock)
    @patch("backend.football.scheduler._sentry_enabled", return_value=False)
    @patch("backend.football.scheduler.get_settings")
    async def test_fires_and_emits_eval_run(
        self, mock_get_settings, _mock_sentry, mock_run_eval, capsys
    ):
        mock_get_settings.return_value = _mock_settings(eval_interval_seconds=0)
        mock_run_eval.return_value = {"ingested": 2, "rollups_written": 16}
        from backend.football.scheduler import start_eval_scheduler

        task = await start_eval_scheduler()
        await asyncio.sleep(0.05)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        assert mock_run_eval.call_count >= 2
        events = [
            json.loads(line)
            for line in capsys.readouterr().out.splitlines()
            if line.strip().startswith("{")
        ]
        eval_runs = [e for e in events if e.get("event") == "eval_run"]
        assert eval_runs, "expected at least one eval_run event"
        assert eval_runs[0]["ingested"] == 2
        assert eval_runs[0]["rollups_written"] == 16


# ── run_evaluation orchestration ─────────────────────────────────────


class TestRunEvaluation:
    async def test_orchestrates_ingest_then_compute(self):
        from backend.football import scheduler

        with patch(
            "backend.football.scripts.ingest_outcomes.run_ingest",
            new=AsyncMock(return_value={"missing": 3, "ingested": 2, "skipped": 1, "errors": 0}),
        ) as mock_ingest, patch(
            "backend.football.scripts.compute_accuracy.run_compute",
            new=AsyncMock(return_value={"pairs": 5, "rollups_written": 16, "with_data": 4}),
        ) as mock_compute:
            result = await scheduler.run_evaluation()

        mock_ingest.assert_awaited_once()
        mock_compute.assert_awaited_once()
        assert result == {"ingested": 2, "rollups_written": 16}


# ── Per-cycle hang guard (EVAL-3 / TRACK-4) ──────────────────────────


class TestEvalHangSurvival:
    """THE TRACK-4 failure mode: run_evaluation hung on an uncapped await for
    12.5h — the broad try/except cannot catch a hang, and there was no
    per-cycle timeout, so the loop went silent forever.  With the wait_for
    guard a hung cycle must raise TimeoutError → be caught → emit
    ``eval_run_timeout`` → and the loop must TICK AGAIN (survive)."""

    @patch("backend.football.scheduler._sentry_enabled", return_value=False)
    @patch("backend.football.scheduler.get_settings")
    async def test_hung_eval_cycle_times_out_and_loop_survives(
        self, mock_get_settings, _mock_sentry, capsys
    ):
        mock_get_settings.return_value = _mock_settings(eval_interval_seconds=0)

        call_count = 0

        async def _hang():
            # Never returns within the (patched-tiny) timeout — exactly the
            # 02:15-UTC stalled-pooler await that froze the outcomes table.
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(10)

        with patch(
            "backend.football.scheduler.run_evaluation", new=_hang
        ), patch(
            "backend.football.scheduler.EVAL_CYCLE_TIMEOUT_SECONDS", 0.01
        ):
            from backend.football.scheduler import start_eval_scheduler

            task = await start_eval_scheduler()
            await asyncio.sleep(0.1)  # let several 0.01s timeouts fire
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        # Survived: the loop did NOT freeze on the first hung cycle — it
        # cancelled it and ticked again (call_count climbs).
        assert call_count >= 2, (
            f"loop froze on the hung cycle (run_evaluation called "
            f"{call_count}x; expected it to recover and tick again)"
        )

        events = [
            json.loads(line)
            for line in capsys.readouterr().out.splitlines()
            if line.strip().startswith("{")
        ]
        timeouts = [e for e in events if e.get("event") == "eval_run_timeout"]
        assert timeouts, "expected an eval_run_timeout tick-error event"
        assert timeouts[0]["timeout_seconds"] == 0.01
        assert timeouts[0]["phase"] == "eval_run"
        # A hung cycle ingests nothing — no success event must be emitted.
        assert not [e for e in events if e.get("event") == "eval_run"]
        # The loop kept running — it did not emit its terminal stop event
        # until the explicit cancel (which we swallow above).
        assert [e for e in events if e.get("event") == "eval_scheduler_stopped"]

    @patch("backend.football.scheduler.run_evaluation", new_callable=AsyncMock)
    @patch("backend.football.scheduler._sentry_enabled", return_value=False)
    @patch("backend.football.scheduler.get_settings")
    async def test_normal_cycle_under_timeout_no_false_trip(
        self, mock_get_settings, _mock_sentry, mock_run_eval, capsys
    ):
        """A fast cycle (the common case) must complete well under the 600s
        timeout and NEVER emit eval_run_timeout — no false positives."""
        mock_get_settings.return_value = _mock_settings(eval_interval_seconds=0)
        mock_run_eval.return_value = {"ingested": 1, "rollups_written": 16}

        from backend.football.scheduler import start_eval_scheduler

        task = await start_eval_scheduler()
        await asyncio.sleep(0.05)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        events = [
            json.loads(line)
            for line in capsys.readouterr().out.splitlines()
            if line.strip().startswith("{")
        ]
        assert [e for e in events if e.get("event") == "eval_run"]
        assert not [e for e in events if e.get("event") == "eval_run_timeout"]
