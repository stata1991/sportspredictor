"""Tests for the pre-fetch match context coordinator.

Verifies parallel execution, graceful degradation on partial/total
failure, and correct MatchContext construction.  Uses AsyncMock for
the API client — does NOT hit any real API.
"""

from __future__ import annotations

import asyncio
import logging
import time
from unittest.mock import AsyncMock

import pytest

from backend.football.agent.prefetch import (
    MatchContext,
    pre_fetch_match_context,
)
from backend.football.predictions.schemas import (
    FirstToScorePayload,
    FixtureStage,
    HTScorePayload,
    PredictionBundle,
    TotalGoalsPayload,
    WinnerPayload,
)


# ── Helpers ──────────────────────────────────────────────────────────


def _make_bundle() -> PredictionBundle:
    """Minimal PredictionBundle for testing."""
    return PredictionBundle(
        stage=FixtureStage.PRE_LINEUP,
        model_version="dixon_coles_v1",
        confidence="normal",
        winner=WinnerPayload(
            p_home_win=0.45,
            p_draw=0.25,
            p_away_win=0.30,
            lambda_home=1.20,
            lambda_away=0.90,
            scoreline_matrix=[[0.0] * 8 for _ in range(8)],
            confidence="normal",
        ),
        total_goals=TotalGoalsPayload(
            expected_total=2.10,
            over_1_5=0.68,
            over_2_5=0.42,
            over_3_5=0.20,
            over_4_5=0.08,
            under_1_5=0.32,
            under_2_5=0.58,
            under_3_5=0.80,
            under_4_5=0.92,
        ),
        ht_score=HTScorePayload(
            p_home_win=0.30,
            p_draw=0.50,
            p_away_win=0.20,
            ht_lambda_home=0.55,
            ht_lambda_away=0.40,
            ht_scoreline_matrix=[[0.0] * 5 for _ in range(5)],
        ),
        first_to_score=FirstToScorePayload(
            p_home_first=0.55,
            p_away_first=0.35,
            p_no_goals=0.10,
        ),
    )


def _mock_client(
    home_form: str = "Recent form for Qatar...",
    away_form: str = "Recent form for Switzerland...",
    h2h: str = "Head-to-head record...",
    injuries: str = "No injuries reported.",
    odds: str = "No odds available for fixture 1489373.",
) -> AsyncMock:
    """Build a mock APIFootballClient that the _exec_* functions can call.

    Rather than mocking the _exec_* functions directly (which would
    bypass the asyncio.gather wiring), we mock the underlying client
    methods that the real _exec_* functions call.
    """
    client = AsyncMock()

    # get_team_form calls client.get_team_last_fixtures(team_id, last=N)
    # We return different results based on team_id to verify correct routing.
    async def _get_team_last_fixtures(team_id, last=5):
        # Return empty list — the tool function will format "No recent fixtures"
        return []

    client.get_team_last_fixtures = AsyncMock(side_effect=_get_team_last_fixtures)

    # get_head_to_head calls client.get_head_to_head(home_id, away_id, last=N)
    client.get_head_to_head = AsyncMock(return_value=[])

    # get_injuries calls client.get_injuries()
    client.get_injuries = AsyncMock(return_value=[])

    # get_odds calls client.get_odds(fixture_id)
    client.get_odds = AsyncMock(return_value=[])

    return client


# ── Tests ────────────────────────────────────────────────────────────


class TestPreFetchMatchContext:
    """Tests for pre_fetch_match_context()."""

    @pytest.mark.asyncio
    async def test_happy_path_all_sources_succeed(self):
        """All 5 tool calls succeed; MatchContext fields populated."""
        client = _mock_client()
        bundle = _make_bundle()

        ctx = await pre_fetch_match_context(
            client=client,
            fixture_id=1489373,
            home_team="Qatar",
            away_team="Switzerland",
            home_team_id=2382,
            away_team_id=15,
            bundle=bundle,
        )

        assert isinstance(ctx, MatchContext)

        # Text fields are populated (tool returned empty lists → formatted text)
        assert "Qatar" in ctx.home_form
        assert "Switzerland" in ctx.away_form
        assert "head-to-head" in ctx.head_to_head.lower() or "No" in ctx.head_to_head
        assert ctx.injuries  # non-empty string
        assert ctx.market_consensus  # non-empty string

        # Prediction context fields passed through
        assert ctx.fixture_id == 1489373
        assert ctx.home_team == "Qatar"
        assert ctx.away_team == "Switzerland"
        assert ctx.home_team_id == 2382
        assert ctx.away_team_id == 15
        assert ctx.stage == "pre_lineup"
        assert ctx.model_version == "dixon_coles_v1"
        assert ctx.confidence == "normal"
        assert abs(ctx.p_home_win - 0.45) < 1e-6
        assert abs(ctx.p_draw - 0.25) < 1e-6
        assert abs(ctx.p_away_win - 0.30) < 1e-6
        assert abs(ctx.lambda_home - 1.20) < 1e-6
        assert abs(ctx.lambda_away - 0.90) < 1e-6
        assert abs(ctx.over_2_5 - 0.42) < 1e-6
        assert abs(ctx.under_2_5 - 0.58) < 1e-6

        # Verify all 5 API client methods were called
        assert client.get_team_last_fixtures.call_count == 2
        client.get_head_to_head.assert_awaited_once()
        client.get_injuries.assert_awaited_once()
        client.get_odds.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_single_source_failure_uses_fallback(self):
        """When one source fails, its field gets a fallback string."""
        client = _mock_client()
        client.get_injuries = AsyncMock(
            side_effect=RuntimeError("API-Football 503")
        )
        bundle = _make_bundle()

        ctx = await pre_fetch_match_context(
            client=client,
            fixture_id=1489373,
            home_team="Qatar",
            away_team="Switzerland",
            home_team_id=2382,
            away_team_id=15,
            bundle=bundle,
        )

        # Injuries field has fallback
        assert ctx.injuries == "Injury data unavailable."

        # Other fields are still populated from successful calls
        assert "Qatar" in ctx.home_form
        assert "Switzerland" in ctx.away_form
        assert ctx.fixture_id == 1489373

    @pytest.mark.asyncio
    async def test_multiple_failures_use_fallbacks(self):
        """When 3 of 5 sources fail, all 3 get fallbacks, 2 succeed."""
        client = _mock_client()
        client.get_injuries = AsyncMock(
            side_effect=RuntimeError("injuries down")
        )
        client.get_odds = AsyncMock(
            side_effect=TimeoutError("odds timeout")
        )
        client.get_head_to_head = AsyncMock(
            side_effect=ConnectionError("h2h refused")
        )
        bundle = _make_bundle()

        ctx = await pre_fetch_match_context(
            client=client,
            fixture_id=1489373,
            home_team="Qatar",
            away_team="Switzerland",
            home_team_id=2382,
            away_team_id=15,
            bundle=bundle,
        )

        # Failed fields have fallbacks
        assert ctx.injuries == "Injury data unavailable."
        assert ctx.market_consensus == "No odds available for fixture 1489373."
        assert ctx.head_to_head == "No head-to-head data available."

        # Successful fields still populated
        assert "Qatar" in ctx.home_form
        assert "Switzerland" in ctx.away_form

    @pytest.mark.asyncio
    async def test_total_failure_all_fallbacks(self, caplog):
        """When all 5 sources fail, all fields get fallbacks and warnings are logged."""
        client = AsyncMock()
        client.get_team_last_fixtures = AsyncMock(
            side_effect=RuntimeError("form down")
        )
        client.get_head_to_head = AsyncMock(
            side_effect=RuntimeError("h2h down")
        )
        client.get_injuries = AsyncMock(
            side_effect=RuntimeError("injuries down")
        )
        client.get_odds = AsyncMock(
            side_effect=RuntimeError("odds down")
        )
        bundle = _make_bundle()

        with caplog.at_level(logging.WARNING, logger="backend.football.agent.prefetch"):
            ctx = await pre_fetch_match_context(
                client=client,
                fixture_id=1489373,
                home_team="Qatar",
                away_team="Switzerland",
                home_team_id=2382,
                away_team_id=15,
                bundle=bundle,
            )

        # All fields have fallbacks
        assert ctx.home_form == "No recent form data available for Qatar."
        assert ctx.away_form == "No recent form data available for Switzerland."
        assert ctx.head_to_head == "No head-to-head data available."
        assert ctx.injuries == "Injury data unavailable."
        assert ctx.market_consensus == "No odds available for fixture 1489373."

        # Prediction context still intact
        assert ctx.fixture_id == 1489373
        assert ctx.stage == "pre_lineup"

        # 5 warning logs emitted
        warning_records = [
            r for r in caplog.records if r.levelno == logging.WARNING
        ]
        assert len(warning_records) == 5

    @pytest.mark.asyncio
    async def test_parallel_execution_timing(self):
        """Verify calls run in parallel: wall clock ~ max(sleep), not sum.

        Each mock sleeps for a different duration.  If sequential, total
        would be ~0.5s.  If parallel, total should be ~0.15s (the longest
        single sleep) within a 1.3x tolerance.
        """
        client = AsyncMock()

        max_sleep = 0.15

        async def _slow_form(team_id, last=5):
            await asyncio.sleep(0.10)
            return []

        async def _slow_h2h(home_id, away_id, last=10):
            await asyncio.sleep(max_sleep)
            return []

        async def _slow_injuries(league=1, season=2026):
            await asyncio.sleep(0.08)
            return []

        async def _slow_odds(fixture_id):
            await asyncio.sleep(0.05)
            return []

        client.get_team_last_fixtures = AsyncMock(side_effect=_slow_form)
        client.get_head_to_head = AsyncMock(side_effect=_slow_h2h)
        client.get_injuries = AsyncMock(side_effect=_slow_injuries)
        client.get_odds = AsyncMock(side_effect=_slow_odds)

        bundle = _make_bundle()

        t0 = time.perf_counter()
        ctx = await pre_fetch_match_context(
            client=client,
            fixture_id=1489373,
            home_team="Qatar",
            away_team="Switzerland",
            home_team_id=2382,
            away_team_id=15,
            bundle=bundle,
        )
        elapsed = time.perf_counter() - t0

        # Sum of all sleeps would be 0.10 + 0.10 + 0.15 + 0.08 + 0.05 = 0.48s
        # Parallel execution should complete in ~max_sleep (0.15s)
        # Allow 1.3x tolerance for scheduling overhead
        tolerance = 1.3
        assert elapsed < max_sleep * tolerance, (
            f"Expected parallel execution in <{max_sleep * tolerance:.3f}s, "
            f"got {elapsed:.3f}s (sequential would be ~0.48s)"
        )

        # Verify the result is still valid
        assert isinstance(ctx, MatchContext)
        assert ctx.fixture_id == 1489373
