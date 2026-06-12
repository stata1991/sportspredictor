"""EVAL-1 dedup: compute replaces-in-place; reader returns latest per cell."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.dml import Delete

from backend.football.persistence import get_all_accuracy_rollups
from backend.football.scripts import compute_accuracy
from backend.shared.models import AccuracyRollup


def _pair():
    pred = MagicMock()
    pred.prediction_type = "winner"
    pred.payload = {"p_home_win": 0.5, "p_draw": 0.3, "p_away_win": 0.2}
    pred.made_at = datetime.now(timezone.utc)
    outcome = MagicMock()
    outcome.ft_home = 2
    outcome.ft_away = 0
    outcome.kickoff_at = datetime(2026, 6, 15, tzinfo=timezone.utc)
    return (pred, outcome)


async def test_run_compute_replaces_in_place():
    """When pairs exist, persist must DELETE the table then add the fresh grid
    in one transaction (idempotent — no duplicate accumulation)."""
    session = MagicMock()
    fetch_res = MagicMock()
    fetch_res.all.return_value = [_pair()]
    session.execute = AsyncMock(side_effect=[fetch_res, MagicMock()])
    session.add_all = MagicMock()
    session.commit = AsyncMock()

    @asynccontextmanager
    async def _ctx():
        yield session

    with patch.object(compute_accuracy, "get_db_session", lambda: _ctx()):
        result = await compute_accuracy.run_compute()

    # Second execute is the DELETE (replace-in-place).
    second_stmt = session.execute.await_args_list[1].args[0]
    assert isinstance(second_stmt, Delete)
    session.add_all.assert_called_once()
    session.commit.assert_awaited_once()
    # 4 windows x 4 prediction types = 16 rows written.
    assert result["rollups_written"] == 16


async def test_reader_uses_distinct_on_latest():
    """get_all_accuracy_rollups must select DISTINCT ON (window, prediction_type)
    ordered by computed_at desc — latest row per cell."""
    captured = {}

    async def _execute(stmt):
        captured["stmt"] = stmt
        res = MagicMock()
        res.scalars.return_value.all.return_value = []
        return res

    session = MagicMock()
    session.execute = _execute

    await get_all_accuracy_rollups(session)

    sql = str(
        captured["stmt"].compile(dialect=postgresql.dialect())
    )
    assert "DISTINCT ON" in sql
    assert "computed_at" in sql
