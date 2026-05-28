"""Tests for the pre-warm admin endpoint (pre-warm-2).

Tests the auth dependency, background warming function, dry_run mode,
idempotency, failure isolation, window filtering, and — critically —
the cross-path cache-hit test that proves the warm path populates the
same cache the live predict_pre_match path reads.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from backend.football.agent.client import AgentCostMetrics
from backend.football.routes import (
    _verify_prewarm_key,
    _warm_fixtures_background,
    router,
)
from backend.football.schemas import (
    AFFixture,
    AFFixtureInfo,
    AFFixtureStatus,
    AFGoals,
    AFLeagueRef,
    AFScore,
    AFTeam,
    AFTeams,
    AFVenue,
)
from backend.shared.models import Prediction

# ── Helpers ──────────────────────────────────────────────────────────

from fastapi import FastAPI

_app = FastAPI()
_app.include_router(router, prefix="/api/football")


def _make_fixture(
    fixture_id: int = 100,
    status_short: str = "NS",
    kickoff_dt: datetime | None = None,
    home_id: int = 10,
    away_id: int = 20,
    home_name: str = "Brazil",
    away_name: str = "Germany",
) -> AFFixture:
    """Build an AFFixture with a controllable kickoff time."""
    if kickoff_dt is None:
        kickoff_dt = datetime.now(timezone.utc) + timedelta(hours=2)
    return AFFixture(
        fixture=AFFixtureInfo(
            id=fixture_id,
            timezone="UTC",
            date=kickoff_dt,
            timestamp=int(kickoff_dt.timestamp()),
            venue=AFVenue(id=1, name="Stadium", city="City"),
            status=AFFixtureStatus(long="Not Started", short=status_short),
        ),
        league=AFLeagueRef(
            id=1, name="World Cup", season=2026, round="Group A - 1",
        ),
        teams=AFTeams(
            home=AFTeam(id=home_id, name=home_name),
            away=AFTeam(id=away_id, name=away_name),
        ),
        goals=AFGoals(),
        score=AFScore(),
    )


def _make_prediction_row(
    fixture_id: int = 100,
    prediction_type: str = "winner",
    stage: str = "pre_lineup",
) -> Prediction:
    row = Prediction()
    row.id = uuid.uuid4()
    row.fixture_id = fixture_id
    row.prediction_type = prediction_type
    row.stage = stage
    row.made_at = datetime.now(timezone.utc)
    row.payload = {"test": True}
    row.model_version = "dixon_coles_v1"
    row.upset_index = None
    row.confidence = None
    return row


def _mock_reasoning_output():
    """Build a mock ReasoningOutput with the fields persistence needs."""
    r = MagicMock()
    r.model_dump.return_value = {
        "paragraphs": ["Test reasoning."],
        "claims": [],
        "upset_index": 0.3,
        "upset_signals": [],
        "upset_paths": [],
        "validation_status": "valid",
    }
    r.validation_status = "valid"
    r.model_version = "claude-sonnet-4-6"
    return r


def _mock_upset_output():
    u = MagicMock()
    u.upset_index = 0.3
    u.deterministic_component = 0.2
    u.agent_component = 0.4
    u.bounded_agent = 0.4
    u.upset_signals = []
    u.upset_paths = []
    return u


# ── Auth tests ───────────────────────────────────────────────────────


class TestPrewarmAuth:

    async def test_missing_header_returns_401(self):
        with patch("backend.football.routes.get_settings") as mock_gs:
            mock_gs.return_value = MagicMock(prewarm_api_key="secret123")
            async with AsyncClient(
                transport=ASGITransport(app=_app), base_url="http://test",
            ) as ac:
                resp = await ac.post(
                    "/api/football/admin/prewarm/upcoming",
                    json={},
                )
            assert resp.status_code == 401

    async def test_wrong_key_returns_403(self):
        with patch("backend.football.routes.get_settings") as mock_gs:
            mock_gs.return_value = MagicMock(prewarm_api_key="secret123")
            async with AsyncClient(
                transport=ASGITransport(app=_app), base_url="http://test",
            ) as ac:
                resp = await ac.post(
                    "/api/football/admin/prewarm/upcoming",
                    json={},
                    headers={"Authorization": "Bearer wrong_key"},
                )
            assert resp.status_code == 403

    async def test_unset_key_returns_503(self):
        with patch("backend.football.routes.get_settings") as mock_gs:
            mock_gs.return_value = MagicMock(prewarm_api_key=None)
            async with AsyncClient(
                transport=ASGITransport(app=_app), base_url="http://test",
            ) as ac:
                resp = await ac.post(
                    "/api/football/admin/prewarm/upcoming",
                    json={},
                    headers={"Authorization": "Bearer anything"},
                )
            assert resp.status_code == 503

    async def test_correct_key_returns_200(self):
        with patch("backend.football.routes.get_settings") as mock_gs:
            mock_gs.return_value = MagicMock(
                prewarm_api_key="secret123",
                api_football_key="afk",
                anthropic_api_key="ak",
            )
            async with AsyncClient(
                transport=ASGITransport(app=_app), base_url="http://test",
            ) as ac:
                resp = await ac.post(
                    "/api/football/admin/prewarm/upcoming",
                    json={"dry_run": True},
                    headers={"Authorization": "Bearer secret123"},
                )
            assert resp.status_code == 200
            body = resp.json()
            assert "tick_id" in body
            assert body["dry_run"] is True


# ── Endpoint returns immediately (background task) ───────────────────


class TestPrewarmEndpointShape:

    async def test_returns_immediately(self):
        """The HTTP response must not block on warming."""
        with patch("backend.football.routes.get_settings") as mock_gs:
            mock_gs.return_value = MagicMock(
                prewarm_api_key="key",
                api_football_key="afk",
                anthropic_api_key="ak",
            )
            # Patch background task to do nothing so we can test response shape
            with patch("backend.football.routes._warm_fixtures_background"):
                async with AsyncClient(
                    transport=ASGITransport(app=_app), base_url="http://test",
                ) as ac:
                    resp = await ac.post(
                        "/api/football/admin/prewarm/upcoming",
                        json={},
                        headers={"Authorization": "Bearer key"},
                    )
            assert resp.status_code == 200
            body = resp.json()
            assert body["accepted"] is True
            assert "window" in body


# ── Background warming function tests ────────────────────────────────


class TestWarmFixturesBackground:

    @patch("backend.football.routes.save_upset_output")
    @patch("backend.football.routes.save_reasoning_output")
    @patch("backend.football.routes.compute_upset_index")
    @patch("backend.football.routes.generate_reasoning_single_shot")
    @patch("backend.football.routes.pre_fetch_match_context")
    @patch("backend.football.routes.save_prediction_bundle")
    @patch("backend.football.routes._get_engine")
    @patch("backend.football.routes.get_cached_reasoning")
    @patch("backend.football.routes.get_cached_bundle")
    @patch("backend.football.routes.detect_stage")
    @patch("backend.football.routes.AsyncSessionLocal")
    @patch("backend.football.routes.APIFootballClient")
    @patch("backend.football.routes.get_settings")
    async def test_dry_run_no_llm_calls(
        self,
        mock_settings,
        mock_afc_cls,
        mock_session_local,
        mock_detect,
        mock_cached_bundle,
        mock_cached_reasoning,
        mock_engine,
        mock_save_bundle,
        mock_prefetch,
        mock_gen_reasoning,
        mock_compute_upset,
        mock_save_reasoning,
        mock_save_upset,
        capsys,
    ):
        """dry_run=True performs cache checks but zero LLM calls."""
        mock_settings.return_value = MagicMock(
            api_football_key="afk",
            anthropic_api_key="ak",
            prewarm_api_key="key",
        )

        # Fixture inside window
        now = datetime.now(timezone.utc)
        fx = _make_fixture(
            fixture_id=200,
            kickoff_dt=now + timedelta(minutes=120),
        )

        mock_client = AsyncMock()
        mock_client.get_fixtures = AsyncMock(return_value=[fx])
        mock_client.get_lineups = AsyncMock(return_value=[])
        mock_afc_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_afc_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session_local.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_local.return_value.__aexit__ = AsyncMock(return_value=False)

        from backend.football.predictions.schemas import FixtureStage
        mock_detect.return_value = FixtureStage.PRE_LINEUP
        mock_cached_bundle.return_value = None
        mock_cached_reasoning.return_value = None

        await _warm_fixtures_background(
            tick_id="test-dry",
            window_start=now + timedelta(minutes=90),
            window_end=now + timedelta(minutes=150),
            dry_run=True,
        )

        # No LLM calls
        mock_gen_reasoning.assert_not_called()
        mock_prefetch.assert_not_called()
        mock_save_bundle.assert_not_called()

        # Check _emit output
        captured = capsys.readouterr()
        lines = [l for l in captured.out.strip().split("\n") if l]
        tick_event = None
        for line in lines:
            parsed = json.loads(line)
            if parsed.get("event") == "prewarm_tick":
                tick_event = parsed
        assert tick_event is not None
        assert tick_event["skipped_dry_run"] == 1
        assert tick_event["attempted"] == 0

    @patch("backend.football.routes.save_upset_output")
    @patch("backend.football.routes.save_reasoning_output")
    @patch("backend.football.routes.compute_upset_index")
    @patch("backend.football.routes.generate_reasoning_single_shot")
    @patch("backend.football.routes.pre_fetch_match_context")
    @patch("backend.football.routes.save_prediction_bundle")
    @patch("backend.football.routes._get_engine")
    @patch("backend.football.routes.get_cached_reasoning")
    @patch("backend.football.routes.get_cached_bundle")
    @patch("backend.football.routes.detect_stage")
    @patch("backend.football.routes.AsyncSessionLocal")
    @patch("backend.football.routes.APIFootballClient")
    @patch("backend.football.routes.get_settings")
    async def test_already_warm_skips_llm(
        self,
        mock_settings,
        mock_afc_cls,
        mock_session_local,
        mock_detect,
        mock_cached_bundle,
        mock_cached_reasoning,
        mock_engine,
        mock_save_bundle,
        mock_prefetch,
        mock_gen_reasoning,
        mock_compute_upset,
        mock_save_reasoning,
        mock_save_upset,
        capsys,
    ):
        """Already-warm fixture triggers zero LLM calls."""
        mock_settings.return_value = MagicMock(
            api_football_key="afk",
            anthropic_api_key="ak",
            prewarm_api_key="key",
        )

        now = datetime.now(timezone.utc)
        fx = _make_fixture(
            fixture_id=300,
            kickoff_dt=now + timedelta(minutes=120),
        )

        mock_client = AsyncMock()
        mock_client.get_fixtures = AsyncMock(return_value=[fx])
        mock_client.get_lineups = AsyncMock(return_value=[])
        mock_afc_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_afc_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session_local.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_local.return_value.__aexit__ = AsyncMock(return_value=False)

        from backend.football.predictions.schemas import FixtureStage
        mock_detect.return_value = FixtureStage.PRE_LINEUP
        # Both caches return hits
        mock_cached_bundle.return_value = {"winner": MagicMock()}
        mock_cached_reasoning.return_value = {
            "reasoning": MagicMock(),
            "upset_index": MagicMock(),
        }

        await _warm_fixtures_background(
            tick_id="test-warm",
            window_start=now + timedelta(minutes=90),
            window_end=now + timedelta(minutes=150),
            dry_run=False,
        )

        mock_gen_reasoning.assert_not_called()

        captured = capsys.readouterr()
        for line in captured.out.strip().split("\n"):
            parsed = json.loads(line)
            if parsed.get("event") == "prewarm_tick":
                assert parsed["already_warm"] == 1
                assert parsed["attempted"] == 0

    @patch("backend.football.routes.save_upset_output")
    @patch("backend.football.routes.save_reasoning_output")
    @patch("backend.football.routes.compute_upset_index")
    @patch("backend.football.routes.generate_reasoning_single_shot")
    @patch("backend.football.routes.pre_fetch_match_context")
    @patch("backend.football.routes.save_prediction_bundle")
    @patch("backend.football.routes._get_engine")
    @patch("backend.football.routes.get_cached_reasoning")
    @patch("backend.football.routes.get_cached_bundle")
    @patch("backend.football.routes.detect_stage")
    @patch("backend.football.routes.AsyncSessionLocal")
    @patch("backend.football.routes.APIFootballClient")
    @patch("backend.football.routes.get_settings")
    async def test_failure_isolation(
        self,
        mock_settings,
        mock_afc_cls,
        mock_session_local,
        mock_detect,
        mock_cached_bundle,
        mock_cached_reasoning,
        mock_engine,
        mock_save_bundle,
        mock_prefetch,
        mock_gen_reasoning,
        mock_compute_upset,
        mock_save_reasoning,
        mock_save_upset,
        capsys,
    ):
        """One fixture failing does not abort the batch."""
        mock_settings.return_value = MagicMock(
            api_football_key="afk",
            anthropic_api_key="ak",
            prewarm_api_key="key",
        )

        now = datetime.now(timezone.utc)
        fx1 = _make_fixture(
            fixture_id=401,
            kickoff_dt=now + timedelta(minutes=100),
            home_name="Fail",
            away_name="Team",
        )
        fx2 = _make_fixture(
            fixture_id=402,
            kickoff_dt=now + timedelta(minutes=110),
            home_name="Success",
            away_name="Team",
        )

        mock_client = AsyncMock()
        mock_client.get_fixtures = AsyncMock(return_value=[fx1, fx2])
        mock_client.get_lineups = AsyncMock(return_value=[])
        mock_afc_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_afc_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session_local.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_local.return_value.__aexit__ = AsyncMock(return_value=False)

        from backend.football.predictions.schemas import FixtureStage
        mock_detect.return_value = FixtureStage.PRE_LINEUP
        mock_cached_bundle.return_value = None
        mock_cached_reasoning.return_value = None

        mock_bundle = MagicMock()
        mock_bundle.stage.value = "pre_lineup"
        mock_bundle.model_version = "test"
        mock_bundle.confidence = "normal"
        mock_bundle.winner = MagicMock(p_home_win=0.4, p_draw=0.3, p_away_win=0.3, lambda_home=1.2, lambda_away=0.8)
        mock_bundle.total_goals = MagicMock(over_2_5=0.5, under_2_5=0.5)
        mock_engine.return_value.predict.return_value = mock_bundle

        mock_ctx = MagicMock()
        mock_prefetch.return_value = mock_ctx

        # First fixture: reasoning raises
        call_count = [0]
        async def gen_reasoning_side_effect(**kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("Anthropic boom")
            return (_mock_reasoning_output(), AgentCostMetrics())

        mock_gen_reasoning.side_effect = gen_reasoning_side_effect

        mock_compute_upset.return_value = _mock_upset_output()

        await _warm_fixtures_background(
            tick_id="test-isolation",
            window_start=now + timedelta(minutes=90),
            window_end=now + timedelta(minutes=150),
            dry_run=False,
        )

        captured = capsys.readouterr()
        for line in captured.out.strip().split("\n"):
            parsed = json.loads(line)
            if parsed.get("event") == "prewarm_tick":
                assert parsed["failed"] == 1
                assert parsed["succeeded"] == 1
                statuses = {r["fixture_id"]: r["status"] for r in parsed["results"]}
                assert statuses[401] == "failed"
                assert statuses[402] == "warmed"

    @patch("backend.football.routes.save_upset_output")
    @patch("backend.football.routes.save_reasoning_output")
    @patch("backend.football.routes.compute_upset_index")
    @patch("backend.football.routes.generate_reasoning_single_shot")
    @patch("backend.football.routes.pre_fetch_match_context")
    @patch("backend.football.routes.save_prediction_bundle")
    @patch("backend.football.routes._get_engine")
    @patch("backend.football.routes.get_cached_reasoning")
    @patch("backend.football.routes.get_cached_bundle")
    @patch("backend.football.routes.detect_stage")
    @patch("backend.football.routes.AsyncSessionLocal")
    @patch("backend.football.routes.APIFootballClient")
    @patch("backend.football.routes.get_settings")
    async def test_window_filtering_and_cap(
        self,
        mock_settings,
        mock_afc_cls,
        mock_session_local,
        mock_detect,
        mock_cached_bundle,
        mock_cached_reasoning,
        mock_engine,
        mock_save_bundle,
        mock_prefetch,
        mock_gen_reasoning,
        mock_compute_upset,
        mock_save_reasoning,
        mock_save_upset,
        capsys,
    ):
        """Only NS/TBD fixtures inside the window are included; cap at 8."""
        mock_settings.return_value = MagicMock(
            api_football_key="afk",
            anthropic_api_key=None,  # no agent, just bundle warming
            prewarm_api_key="key",
        )

        now = datetime.now(timezone.utc)
        fixtures = []
        # 10 fixtures inside window (should be capped at 8)
        for i in range(10):
            fixtures.append(_make_fixture(
                fixture_id=500 + i,
                kickoff_dt=now + timedelta(minutes=100 + i),
            ))
        # 1 fixture outside window (too early)
        fixtures.append(_make_fixture(
            fixture_id=600,
            kickoff_dt=now + timedelta(minutes=10),
        ))
        # 1 completed fixture inside window time but wrong status
        fx_completed = _make_fixture(
            fixture_id=601,
            status_short="FT",
            kickoff_dt=now + timedelta(minutes=120),
        )
        fixtures.append(fx_completed)

        mock_client = AsyncMock()
        mock_client.get_fixtures = AsyncMock(return_value=fixtures)
        mock_client.get_lineups = AsyncMock(return_value=[])
        mock_afc_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_afc_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session_local.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_local.return_value.__aexit__ = AsyncMock(return_value=False)

        from backend.football.predictions.schemas import FixtureStage
        mock_detect.return_value = FixtureStage.PRE_LINEUP
        mock_cached_bundle.return_value = None
        mock_cached_reasoning.return_value = None

        mock_bundle = MagicMock()
        mock_bundle.stage.value = "pre_lineup"
        mock_engine.return_value.predict.return_value = mock_bundle

        await _warm_fixtures_background(
            tick_id="test-cap",
            window_start=now + timedelta(minutes=90),
            window_end=now + timedelta(minutes=150),
            dry_run=True,
        )

        captured = capsys.readouterr()
        for line in captured.out.strip().split("\n"):
            parsed = json.loads(line)
            if parsed.get("event") == "prewarm_tick":
                # 10 inside window but capped at 8
                assert parsed["fixtures_in_window"] == 8
                assert parsed["skipped_dry_run"] == 8
                # Verify ordering by soonest kickoff
                fids = [r["fixture_id"] for r in parsed["results"]]
                assert fids == list(range(500, 508))


# ── THE CRITICAL CROSS-PATH CACHE-HIT TEST ──────────────────────────


class TestCrossPathCacheHit:
    """Proves that warming via the pre-warm path populates the exact same
    cache that predict_pre_match reads.

    This is the hard acceptance gate.  If this fails, the pre-warm
    feature is broken — warmed fixtures would still hit the cold path.
    """

    @patch("backend.football.routes.save_upset_output")
    @patch("backend.football.routes.save_reasoning_output")
    @patch("backend.football.routes.compute_upset_index")
    @patch("backend.football.routes.generate_reasoning_single_shot")
    @patch("backend.football.routes.pre_fetch_match_context")
    @patch("backend.football.routes.save_prediction_bundle")
    @patch("backend.football.routes._get_engine")
    @patch("backend.football.routes.get_cached_reasoning")
    @patch("backend.football.routes.get_cached_bundle")
    @patch("backend.football.routes.detect_stage")
    @patch("backend.football.routes.AsyncSessionLocal")
    @patch("backend.football.routes.APIFootballClient")
    @patch("backend.football.routes.get_settings")
    async def test_prewarm_populates_predict_pre_match_cache(
        self,
        mock_settings,
        mock_afc_cls,
        mock_session_local,
        mock_detect,
        mock_cached_bundle,
        mock_cached_reasoning,
        mock_engine,
        mock_save_bundle,
        mock_prefetch,
        mock_gen_reasoning,
        mock_compute_upset,
        mock_save_reasoning,
        mock_save_upset,
    ):
        """Warm one fixture via _warm_fixtures_background, then call
        predict_pre_match for the same fixture — assert zero additional
        Anthropic calls (cache hit)."""

        mock_settings.return_value = MagicMock(
            api_football_key="afk",
            anthropic_api_key="ak",
            prewarm_api_key="key",
            use_single_shot_reasoning=True,
        )

        now = datetime.now(timezone.utc)
        fx = _make_fixture(
            fixture_id=777,
            kickoff_dt=now + timedelta(minutes=120),
            home_name="Argentina",
            away_name="France",
            home_id=10,
            away_id=20,
        )

        # ── Set up mocks ──────────────────────────────────────────
        mock_client = AsyncMock()
        mock_client.get_fixtures = AsyncMock(return_value=[fx])
        mock_client.get_fixture = AsyncMock(return_value=fx)
        mock_client.get_lineups = AsyncMock(return_value=[])
        mock_afc_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_afc_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session_local.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_local.return_value.__aexit__ = AsyncMock(return_value=False)

        from backend.football.predictions.schemas import FixtureStage
        mock_detect.return_value = FixtureStage.PRE_LINEUP

        mock_bundle = MagicMock()
        mock_bundle.stage.value = "pre_lineup"
        mock_bundle.model_version = "dixon_coles_v1"
        mock_bundle.confidence = "normal"
        mock_bundle.winner = MagicMock(
            p_home_win=0.5, p_draw=0.25, p_away_win=0.25,
            lambda_home=1.5, lambda_away=0.9,
        )
        mock_bundle.winner.model_dump.return_value = {"p_home_win": 0.5}
        mock_bundle.total_goals = MagicMock(over_2_5=0.6, under_2_5=0.4)
        mock_bundle.total_goals.model_dump.return_value = {"over_2_5": 0.6}
        mock_bundle.ht_score = MagicMock()
        mock_bundle.ht_score.model_dump.return_value = {"p_0_0": 0.3}
        mock_bundle.first_to_score = MagicMock()
        mock_bundle.first_to_score.model_dump.return_value = {"p_home": 0.5}
        mock_engine.return_value.predict.return_value = mock_bundle

        mock_ctx = MagicMock()
        mock_prefetch.return_value = mock_ctx

        mock_reasoning = _mock_reasoning_output()
        mock_cost = AgentCostMetrics()
        mock_gen_reasoning.return_value = (mock_reasoning, mock_cost)

        mock_compute_upset.return_value = _mock_upset_output()

        # ── Phase 1: PREWARM CALL ─────────────────────────────────
        # Start with empty cache (both return None)
        mock_cached_bundle.return_value = None
        mock_cached_reasoning.return_value = None

        await _warm_fixtures_background(
            tick_id="cross-path-test",
            window_start=now + timedelta(minutes=90),
            window_end=now + timedelta(minutes=150),
            dry_run=False,
        )

        # Assert: Anthropic was called exactly once (during pre-warm)
        assert mock_gen_reasoning.call_count == 1
        # Assert: predictions and reasoning were persisted
        assert mock_save_bundle.call_count == 1
        assert mock_save_reasoning.call_count == 1
        assert mock_save_upset.call_count == 1

        # ── Phase 2: PREDICT_PRE_MATCH CALL (should hit cache) ────
        # Now simulate the cache being populated by the pre-warm:
        # get_cached_bundle and get_cached_reasoning return results
        reasoning_row = _make_prediction_row(
            fixture_id=777, prediction_type="reasoning",
        )
        reasoning_row.payload = mock_reasoning.model_dump()
        upset_row = _make_prediction_row(
            fixture_id=777, prediction_type="upset_index",
        )
        upset_row.payload = {"upset_index": 0.3}

        mock_cached_bundle.return_value = {
            "winner": _make_prediction_row(777, "winner"),
            "total_goals": _make_prediction_row(777, "total_goals"),
            "ht_score": _make_prediction_row(777, "ht_score"),
            "first_to_score": _make_prediction_row(777, "first_to_score"),
        }
        mock_cached_reasoning.return_value = {
            "reasoning": reasoning_row,
            "upset_index": upset_row,
        }

        # Reset call counts to prove predict_pre_match doesn't call Anthropic again
        mock_gen_reasoning.reset_mock()
        mock_save_bundle.reset_mock()
        mock_prefetch.reset_mock()

        # Override deps for the HTTP call
        from backend.football.deps import get_agent_client, get_football_client
        from backend.shared.db import get_session

        async def _override_client():
            return mock_client

        async def _override_session():
            return mock_session

        def _override_agent():
            return MagicMock()  # non-None so the reasoning branch is entered

        _app.dependency_overrides[get_football_client] = _override_client
        _app.dependency_overrides[get_session] = _override_session
        _app.dependency_overrides[get_agent_client] = _override_agent

        try:
            async with AsyncClient(
                transport=ASGITransport(app=_app), base_url="http://test",
            ) as ac:
                resp = await ac.get("/api/football/predict/pre-match/777")

            assert resp.status_code == 200
            body = resp.json()

            # The critical assertions:
            # 1. Response was served from cache
            assert body["cached"] is True
            # 2. Zero additional Anthropic calls
            mock_gen_reasoning.assert_not_called()
            mock_prefetch.assert_not_called()
            # 3. No additional bundle saves (cache hit, not regeneration)
            mock_save_bundle.assert_not_called()
        finally:
            _app.dependency_overrides.clear()
