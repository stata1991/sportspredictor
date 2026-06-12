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
