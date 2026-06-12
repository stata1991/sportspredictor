"""Tests for the outcome ingestion script (EVAL-1 status gating).

Verifies: FT/AET/PEN ingested; NS/live/PST/CANC skipped; idempotent re-run
(no missing fixtures) writes nothing.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.football.scripts import ingest_outcomes


def _mock_fixture(status_short: str, ft_home=2, ft_away=0):
    fx = MagicMock()
    fx.fixture.status.short = status_short
    fx.fixture.date = "2026-06-11T19:00:00+00:00"
    fx.teams.home.name = "Mexico"
    fx.teams.away.name = "South Africa"
    fx.score.fulltime.home = ft_home
    fx.score.fulltime.away = ft_away
    fx.score.halftime.home = 1
    fx.score.halftime.away = 0
    return fx


def _patch_db(predicted_ids, existing_ids):
    """Patch get_db_session: Phase-1 execute returns predicted then existing."""
    session = MagicMock()
    predicted_res = MagicMock()
    predicted_res.scalars.return_value.all.return_value = list(predicted_ids)
    existing_res = MagicMock()
    existing_res.scalars.return_value.all.return_value = list(existing_ids)
    session.execute = AsyncMock(side_effect=[predicted_res, existing_res])
    session.commit = AsyncMock()

    @asynccontextmanager
    async def _ctx():
        yield session

    return patch.object(ingest_outcomes, "get_db_session", lambda: _ctx()), session


def _patch_client(fixture, events=None):
    client = MagicMock()
    client.get_fixture = AsyncMock(return_value=fixture)
    client.get_events = AsyncMock(return_value=events or [])

    @asynccontextmanager
    async def _ctx(*_a, **_k):
        yield client

    return patch.object(ingest_outcomes, "APIFootballClient", lambda *a, **k: _ctx())


def _goal(team_name: str, elapsed: int, etype: str = "Goal"):
    e = MagicMock()
    e.type = etype
    e.team.name = team_name
    e.time.elapsed = elapsed
    e.time.extra = None
    return e


class TestFirstScorerTeam:
    def test_no_goals_returns_none(self):
        events = [_goal("Mexico", 30, etype="Card")]
        assert ingest_outcomes._first_scorer_team(events) is None

    def test_returns_earliest_goal_team(self):
        events = [
            _goal("Mexico", 67),
            _goal("South Africa", 12),
            _goal("Mexico", 9),
        ]
        assert ingest_outcomes._first_scorer_team(events) == "Mexico"

    def test_first_goal_team_when_in_order(self):
        # Opener: Mexico scored first at 9'.
        events = [_goal("Mexico", 9), _goal("Mexico", 67)]
        assert ingest_outcomes._first_scorer_team(events) == "Mexico"


@pytest.mark.parametrize(
    "status,should_ingest",
    [
        ("FT", True),
        ("AET", True),
        ("PEN", True),
        ("NS", False),
        ("1H", False),   # live
        ("HT", False),   # live
        ("PST", False),
        ("CANC", False),
    ],
)
async def test_status_gating(status, should_ingest):
    db_patch, _session = _patch_db(predicted_ids={100}, existing_ids=set())
    with db_patch, _patch_client(_mock_fixture(status)), patch.object(
        ingest_outcomes, "save_outcome", new=AsyncMock()
    ) as mock_save, patch.object(
        ingest_outcomes, "CacheClient", MagicMock()
    ), patch.object(
        ingest_outcomes, "AsyncSingleflight", MagicMock()
    ), patch.object(
        ingest_outcomes, "get_settings",
        return_value=MagicMock(api_football_key="k"),
    ):
        result = await ingest_outcomes.run_ingest()

    if should_ingest:
        assert result["ingested"] == 1
        mock_save.assert_awaited_once()
    else:
        assert result["ingested"] == 0
        assert result["skipped"] == 1
        mock_save.assert_not_awaited()


async def test_idempotent_no_missing_writes_nothing():
    # Everything predicted already has an outcome → nothing to ingest.
    db_patch, _session = _patch_db(predicted_ids={100, 200}, existing_ids={100, 200})
    with db_patch, patch.object(
        ingest_outcomes, "save_outcome", new=AsyncMock()
    ) as mock_save, patch.object(
        ingest_outcomes, "get_settings",
        return_value=MagicMock(api_football_key="k"),
    ):
        result = await ingest_outcomes.run_ingest()

    assert result == {"missing": 0, "ingested": 0, "skipped": 0, "errors": 0}
    mock_save.assert_not_awaited()
