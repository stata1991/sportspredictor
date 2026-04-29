"""Tests for the football prediction route endpoints (5.2.5).

Uses mock dependencies — does NOT call the real API-Football API
or write to the database.  Verifies route logic, exception handling,
and response structure.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from backend.football.routes import _get_engine, router
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
from backend.shared.models import AccuracyRollup, Prediction

# ── Helpers ──────────────────────────────────────────────────────────

# Minimal FastAPI app with just the football router.
from fastapi import FastAPI

_app = FastAPI()
_app.include_router(router, prefix="/api/football")


def _make_fixture(
    fixture_id: int = 100,
    status_short: str = "NS",
    status_long: str = "Not Started",
    home_id: int = 10,
    away_id: int = 20,
    home_name: str = "Brazil",
    away_name: str = "Germany",
    elapsed: int | None = None,
    home_goals: int | None = None,
    away_goals: int | None = None,
) -> AFFixture:
    """Build a minimal AFFixture for route tests."""
    return AFFixture(
        fixture=AFFixtureInfo(
            id=fixture_id,
            timezone="UTC",
            date=datetime(2026, 6, 11, 18, 0, tzinfo=timezone.utc),
            timestamp=1781366400,
            venue=AFVenue(id=1, name="Stadium", city="City"),
            status=AFFixtureStatus(
                long=status_long, short=status_short, elapsed=elapsed
            ),
        ),
        league=AFLeagueRef(
            id=1, name="World Cup", season=2026, round="Group A - 1"
        ),
        teams=AFTeams(
            home=AFTeam(id=home_id, name=home_name),
            away=AFTeam(id=away_id, name=away_name),
        ),
        goals=AFGoals(home=home_goals, away=away_goals),
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


# ── Pre-match endpoint ───────────────────────────────────────────────


class TestPredictPreMatch:
    @pytest.fixture(autouse=True)
    def _setup_deps(self):
        """Override FastAPI dependencies for all tests in this class."""
        self.mock_client = AsyncMock()
        self.mock_session = AsyncMock()
        self.mock_session.commit = AsyncMock()

        async def _override_client():
            return self.mock_client

        async def _override_session():
            return self.mock_session

        _app.dependency_overrides.clear()
        from backend.football.deps import get_football_client
        from backend.shared.db import get_session

        _app.dependency_overrides[get_football_client] = _override_client
        _app.dependency_overrides[get_session] = _override_session

        yield
        _app.dependency_overrides.clear()

    async def test_fixture_not_found_returns_404(self):
        self.mock_client.get_fixture = AsyncMock(return_value=None)

        async with AsyncClient(
            transport=ASGITransport(app=_app), base_url="http://test"
        ) as ac:
            resp = await ac.get("/api/football/predict/pre-match/999")

        assert resp.status_code == 404

    async def test_not_predictable_returns_422(self):
        fx = _make_fixture(status_short="CANC", status_long="Cancelled")
        self.mock_client.get_fixture = AsyncMock(return_value=fx)

        async with AsyncClient(
            transport=ASGITransport(app=_app), base_url="http://test"
        ) as ac:
            resp = await ac.get("/api/football/predict/pre-match/100")

        assert resp.status_code == 422

    async def test_live_status_returns_422(self):
        fx = _make_fixture(
            status_short="1H", status_long="First Half", elapsed=30
        )
        self.mock_client.get_fixture = AsyncMock(return_value=fx)

        async with AsyncClient(
            transport=ASGITransport(app=_app), base_url="http://test"
        ) as ac:
            resp = await ac.get("/api/football/predict/pre-match/100")

        assert resp.status_code == 422

    @patch("backend.football.routes.get_cached_bundle")
    @patch("backend.football.routes._get_engine")
    async def test_generates_fresh_predictions(
        self, mock_engine_fn, mock_cache_fn
    ):
        fx = _make_fixture()
        self.mock_client.get_fixture = AsyncMock(return_value=fx)
        self.mock_client.get_lineups = AsyncMock(return_value=[])
        mock_cache_fn.return_value = None  # no cache

        # Create a mock engine that returns a real-ish bundle.
        mock_engine = MagicMock()
        mock_bundle = MagicMock()
        mock_bundle.stage.value = "pre_lineup"
        mock_bundle.model_version = "dixon_coles_v1"
        mock_bundle.confidence = "normal"
        mock_bundle.winner.model_dump.return_value = {"p_home_win": 0.4}
        mock_bundle.total_goals.model_dump.return_value = {
            "over_2_5": 0.5
        }
        mock_bundle.ht_score.model_dump.return_value = {"p_draw": 0.3}
        mock_bundle.first_to_score.model_dump.return_value = {
            "p_home_first": 0.5
        }
        mock_engine.predict.return_value = mock_bundle
        mock_engine_fn.return_value = mock_engine

        # Mock save_prediction_bundle
        with patch(
            "backend.football.routes.save_prediction_bundle"
        ) as mock_save:
            mock_save.return_value = []

            async with AsyncClient(
                transport=ASGITransport(app=_app), base_url="http://test"
            ) as ac:
                resp = await ac.get(
                    "/api/football/predict/pre-match/100"
                )

        assert resp.status_code == 200
        body = resp.json()
        assert body["cached"] is False
        assert body["stage"] == "pre_lineup"
        assert "predictions" in body
        mock_save.assert_awaited_once()

    @patch("backend.football.routes.get_cached_bundle")
    async def test_returns_cached_when_fresh(self, mock_cache_fn):
        fx = _make_fixture()
        self.mock_client.get_fixture = AsyncMock(return_value=fx)
        self.mock_client.get_lineups = AsyncMock(return_value=[])

        mock_cache_fn.return_value = {
            t: _make_prediction_row(prediction_type=t)
            for t in ("winner", "total_goals", "ht_score", "first_to_score")
        }

        async with AsyncClient(
            transport=ASGITransport(app=_app), base_url="http://test"
        ) as ac:
            resp = await ac.get("/api/football/predict/pre-match/100")

        assert resp.status_code == 200
        body = resp.json()
        assert body["cached"] is True

    @patch(
        "backend.football.routes.get_latest_predictions_for_fixture"
    )
    async def test_completed_returns_200_with_historical(
        self, mock_latest
    ):
        fx = _make_fixture(
            status_short="FT", status_long="Match Finished"
        )
        self.mock_client.get_fixture = AsyncMock(return_value=fx)

        mock_latest.return_value = {
            "winner": _make_prediction_row(prediction_type="winner"),
        }

        async with AsyncClient(
            transport=ASGITransport(app=_app), base_url="http://test"
        ) as ac:
            resp = await ac.get("/api/football/predict/pre-match/100")

        assert resp.status_code == 200
        body = resp.json()
        assert body["stage"] == "completed"
        assert "predictions" in body


# ── Live endpoint ────────────────────────────────────────────────────


class TestPredictLive:
    @pytest.fixture(autouse=True)
    def _setup_deps(self):
        self.mock_client = AsyncMock()
        self.mock_session = AsyncMock()
        self.mock_session.commit = AsyncMock()

        async def _override_client():
            return self.mock_client

        async def _override_session():
            return self.mock_session

        _app.dependency_overrides.clear()
        from backend.football.deps import get_football_client
        from backend.shared.db import get_session

        _app.dependency_overrides[get_football_client] = _override_client
        _app.dependency_overrides[get_session] = _override_session

        yield
        _app.dependency_overrides.clear()

    async def test_not_started_returns_422(self):
        fx = _make_fixture(status_short="NS")
        self.mock_client.get_fixture = AsyncMock(return_value=fx)

        async with AsyncClient(
            transport=ASGITransport(app=_app), base_url="http://test"
        ) as ac:
            resp = await ac.get("/api/football/predict/live/100")

        assert resp.status_code == 422

    async def test_not_predictable_returns_422(self):
        fx = _make_fixture(status_short="PST", status_long="Postponed")
        self.mock_client.get_fixture = AsyncMock(return_value=fx)

        async with AsyncClient(
            transport=ASGITransport(app=_app), base_url="http://test"
        ) as ac:
            resp = await ac.get("/api/football/predict/live/100")

        assert resp.status_code == 422

    @patch("backend.football.routes.save_live_prediction")
    @patch("backend.football.routes.get_cached_live_prediction")
    @patch("backend.football.routes._get_engine")
    async def test_live_generates_and_persists(
        self, mock_engine_fn, mock_cache_fn, mock_save_fn
    ):
        fx = _make_fixture(
            status_short="1H",
            status_long="First Half",
            elapsed=30,
            home_goals=1,
            away_goals=0,
        )
        self.mock_client.get_fixture = AsyncMock(return_value=fx)
        mock_cache_fn.return_value = None  # no cache

        mock_engine = MagicMock()
        mock_engine.model.predict_match.return_value = {
            "lambda_home": 1.5,
            "lambda_away": 1.0,
            "confidence": "normal",
        }
        mock_engine_fn.return_value = mock_engine
        mock_save_fn.return_value = MagicMock()

        async with AsyncClient(
            transport=ASGITransport(app=_app), base_url="http://test"
        ) as ac:
            resp = await ac.get("/api/football/predict/live/100")

        assert resp.status_code == 200
        body = resp.json()
        assert body["stage"] == "live"
        assert body["cached"] is False
        live = body["predictions"]["live_winner"]
        assert live["method"] == "v1_lambda_remaining"
        assert live["elapsed"] == 30
        total = (
            live["p_home_win"] + live["p_draw"] + live["p_away_win"]
        )
        assert abs(total - 1.0) < 1e-4

        # Verify persistence was called.
        mock_save_fn.assert_awaited_once()
        self.mock_session.commit.assert_awaited_once()

    @patch("backend.football.routes.get_cached_live_prediction")
    async def test_live_returns_cached_when_fresh(self, mock_cache_fn):
        fx = _make_fixture(
            status_short="2H",
            status_long="Second Half",
            elapsed=60,
            home_goals=1,
            away_goals=1,
        )
        self.mock_client.get_fixture = AsyncMock(return_value=fx)

        cached_row = _make_prediction_row(
            prediction_type="live_winner", stage="live"
        )
        cached_row.payload = {
            "method": "v1_lambda_remaining",
            "elapsed": 60,
            "p_home_win": 0.35,
            "p_draw": 0.40,
            "p_away_win": 0.25,
        }
        mock_cache_fn.return_value = cached_row

        async with AsyncClient(
            transport=ASGITransport(app=_app), base_url="http://test"
        ) as ac:
            resp = await ac.get("/api/football/predict/live/100")

        assert resp.status_code == 200
        body = resp.json()
        assert body["cached"] is True
        assert body["predictions"]["live_winner"]["elapsed"] == 60


# ── History endpoint ─────────────────────────────────────────────────


class TestPredictionHistory:
    @pytest.fixture(autouse=True)
    def _setup_deps(self):
        self.mock_session = AsyncMock()

        async def _override_session():
            return self.mock_session

        _app.dependency_overrides.clear()
        from backend.shared.db import get_session

        _app.dependency_overrides[get_session] = _override_session

        yield
        _app.dependency_overrides.clear()

    @patch("backend.football.routes.get_predictions_for_fixture")
    async def test_returns_predictions(self, mock_get):
        mock_get.return_value = [
            _make_prediction_row(prediction_type="winner"),
            _make_prediction_row(prediction_type="total_goals"),
        ]

        async with AsyncClient(
            transport=ASGITransport(app=_app), base_url="http://test"
        ) as ac:
            resp = await ac.get(
                "/api/football/predictions/history/100"
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 2
        assert body["fixture_id"] == 100
        assert len(body["predictions"]) == 2

    @patch("backend.football.routes.get_predictions_for_fixture")
    async def test_empty_history(self, mock_get):
        mock_get.return_value = []

        async with AsyncClient(
            transport=ASGITransport(app=_app), base_url="http://test"
        ) as ac:
            resp = await ac.get(
                "/api/football/predictions/history/999"
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 0
        assert body["predictions"] == []


# ── Accuracy endpoint ────────────────────────────────────────────────


class TestAccuracy:
    @pytest.fixture(autouse=True)
    def _setup_deps(self):
        self.mock_session = AsyncMock()

        async def _override_session():
            return self.mock_session

        _app.dependency_overrides.clear()
        from backend.shared.db import get_session

        _app.dependency_overrides[get_session] = _override_session

        yield
        _app.dependency_overrides.clear()

    @patch("backend.football.routes.get_all_accuracy_rollups")
    async def test_empty_rollups(self, mock_get):
        mock_get.return_value = []

        async with AsyncClient(
            transport=ASGITransport(app=_app), base_url="http://test"
        ) as ac:
            resp = await ac.get("/api/football/accuracy")

        assert resp.status_code == 200
        body = resp.json()
        assert body["rollups"] == []
        assert "message" in body

    @patch("backend.football.routes.get_all_accuracy_rollups")
    async def test_returns_rollups(self, mock_get):
        rollup = AccuracyRollup()
        rollup.id = uuid.uuid4()
        rollup.window = "last_7d"
        rollup.prediction_type = "winner"
        rollup.total_predictions = 10
        rollup.brier_score = None
        rollup.log_loss = None
        rollup.top_pick_hit_rate = None
        rollup.computed_at = datetime(
            2026, 6, 15, 12, 0, tzinfo=timezone.utc
        )

        mock_get.return_value = [rollup]

        async with AsyncClient(
            transport=ASGITransport(app=_app), base_url="http://test"
        ) as ac:
            resp = await ac.get("/api/football/accuracy")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body["rollups"]) == 1
        assert body["rollups"][0]["window"] == "last_7d"
        assert body["rollups"][0]["total_predictions"] == 10
