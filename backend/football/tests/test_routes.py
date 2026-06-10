"""Tests for the football prediction route endpoints (5.2.5).

Uses mock dependencies — does NOT call the real API-Football API
or write to the database.  Verifies route logic, exception handling,
and response structure.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from backend.football.routes import _emit_unknown_round, _get_engine, router
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

# ── Unknown-round tripwire (KO-5) ─────────────────────────────────────


class TestUnknownRoundTripwire:
    def test_unknown_round_emits_event(self, capsys):
        emitted = _emit_unknown_round("Round of 64", 12345)
        assert emitted is True
        out = capsys.readouterr().out
        assert '"event": "unknown_round_string"' in out
        assert '"round": "Round of 64"' in out
        assert '"fixture_id": 12345' in out

    @pytest.mark.parametrize(
        "round_str",
        ["Round of 16", "Final", "Group Stage - 2", None],
    )
    def test_known_or_none_does_not_emit(self, capsys, round_str):
        emitted = _emit_unknown_round(round_str, 1)
        assert emitted is False
        assert capsys.readouterr().out == ""


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

        def _override_agent():
            return None  # No agent by default in existing tests.

        _app.dependency_overrides.clear()
        from backend.football.deps import get_agent_client, get_football_client
        from backend.shared.db import get_session

        _app.dependency_overrides[get_football_client] = _override_client
        _app.dependency_overrides[get_session] = _override_session
        _app.dependency_overrides[get_agent_client] = _override_agent

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
        # No agent configured → reasoning and upset are null.
        assert body["reasoning"] is None
        assert body["upset"] is None
        mock_save.assert_awaited_once()

    @patch("backend.football.routes.get_cached_reasoning")
    @patch("backend.football.routes.get_cached_bundle")
    async def test_returns_cached_when_fresh(
        self, mock_cache_fn, mock_cache_reasoning_fn
    ):
        fx = _make_fixture()
        self.mock_client.get_fixture = AsyncMock(return_value=fx)
        self.mock_client.get_lineups = AsyncMock(return_value=[])

        mock_cache_fn.return_value = {
            t: _make_prediction_row(prediction_type=t)
            for t in ("winner", "total_goals", "ht_score", "first_to_score")
        }
        mock_cache_reasoning_fn.return_value = None

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


# ── Reasoning wiring tests ──────────────────────────────────────────


class TestPredictPreMatchWithReasoning:
    """Tests for reasoning + upset integration in predict_pre_match."""

    @pytest.fixture(autouse=True)
    def _setup_deps(self):
        self.mock_client = AsyncMock()
        self.mock_session = AsyncMock()
        self.mock_session.commit = AsyncMock()
        self.mock_agent = MagicMock()

        async def _override_client():
            return self.mock_client

        async def _override_session():
            return self.mock_session

        def _override_agent():
            return self.mock_agent

        _app.dependency_overrides.clear()
        from backend.football.deps import get_agent_client, get_football_client
        from backend.shared.db import get_session

        _app.dependency_overrides[get_football_client] = _override_client
        _app.dependency_overrides[get_session] = _override_session
        _app.dependency_overrides[get_agent_client] = _override_agent

        yield
        _app.dependency_overrides.clear()

    def _setup_fresh_prediction(self, mock_engine_fn, mock_cache_fn):
        """Common setup for fresh prediction tests."""
        fx = _make_fixture()
        self.mock_client.get_fixture = AsyncMock(return_value=fx)
        self.mock_client.get_lineups = AsyncMock(return_value=[])
        mock_cache_fn.return_value = None

        mock_engine = MagicMock()
        mock_bundle = MagicMock()
        mock_bundle.stage.value = "pre_lineup"
        mock_bundle.model_version = "dixon_coles_v1"
        mock_bundle.confidence = "normal"
        mock_bundle.winner.model_dump.return_value = {"p_home_win": 0.4}
        mock_bundle.total_goals.model_dump.return_value = {"over_2_5": 0.5}
        mock_bundle.ht_score.model_dump.return_value = {"p_draw": 0.3}
        mock_bundle.first_to_score.model_dump.return_value = {
            "p_home_first": 0.5
        }
        mock_engine.predict.return_value = mock_bundle
        mock_engine_fn.return_value = mock_engine
        return mock_bundle

    @patch("backend.football.routes.get_settings")
    @patch("backend.football.routes.compute_upset_index")
    @patch("backend.football.routes.generate_reasoning")
    @patch("backend.football.routes.save_upset_output")
    @patch("backend.football.routes.save_reasoning_output")
    @patch("backend.football.routes.save_prediction_bundle")
    @patch("backend.football.routes.get_cached_reasoning")
    @patch("backend.football.routes.get_cached_bundle")
    @patch("backend.football.routes._get_engine")
    async def test_reasoning_generated_on_fresh_prediction(
        self,
        mock_engine_fn,
        mock_cache_fn,
        mock_cache_reasoning_fn,
        mock_save_bundle,
        mock_save_reasoning,
        mock_save_upset,
        mock_gen_reasoning,
        mock_compute_upset,
        mock_get_settings,
    ):
        self._setup_fresh_prediction(mock_engine_fn, mock_cache_fn)
        mock_save_bundle.return_value = []
        mock_cache_reasoning_fn.return_value = None

        # Force agent-loop path for this test.
        mock_settings = MagicMock()
        mock_settings.use_single_shot_reasoning = False
        mock_get_settings.return_value = mock_settings

        # Mock reasoning output.
        mock_reasoning = MagicMock()
        mock_reasoning.paragraphs = ["P1.", "P2.", "P3."]
        mock_reasoning.claims = []
        mock_reasoning.upset_index = 0.40
        mock_reasoning.upset_signals = []
        mock_reasoning.upset_paths = []
        mock_reasoning.validation_status = "valid"
        mock_cost = MagicMock()
        mock_cost.input_tokens = 100
        mock_cost.output_tokens = 50
        mock_cost.cache_creation_input_tokens = 0
        mock_cost.cache_read_input_tokens = 0
        mock_gen_reasoning.return_value = (mock_reasoning, mock_cost)

        # Mock upset output.
        mock_upset = MagicMock()
        mock_upset.upset_index = 0.28
        mock_upset.deterministic_component = 0.22
        mock_upset.agent_component = 0.40
        mock_upset.bounded_agent = 0.37
        mock_upset.upset_signals = []
        mock_upset.upset_paths = []
        mock_compute_upset.return_value = mock_upset

        mock_save_reasoning.return_value = MagicMock()
        mock_save_upset.return_value = MagicMock()

        async with AsyncClient(
            transport=ASGITransport(app=_app), base_url="http://test"
        ) as ac:
            resp = await ac.get("/api/football/predict/pre-match/100")

        assert resp.status_code == 200
        body = resp.json()
        assert body["reasoning"] is not None
        assert body["reasoning"]["paragraphs"] == ["P1.", "P2.", "P3."]
        assert body["reasoning"]["validation_status"] == "valid"
        assert body["upset"] is not None
        assert body["upset"]["upset_index"] == 0.28
        mock_save_reasoning.assert_awaited_once()
        mock_save_upset.assert_awaited_once()
        # Two commits: one for deterministic, one for reasoning+upset.
        assert self.mock_session.commit.await_count == 2

    @patch("backend.football.routes.get_settings")
    @patch("backend.football.routes.generate_reasoning")
    @patch("backend.football.routes.save_prediction_bundle")
    @patch("backend.football.routes.get_cached_reasoning")
    @patch("backend.football.routes.get_cached_bundle")
    @patch("backend.football.routes._get_engine")
    async def test_reasoning_failure_returns_prediction_with_null(
        self,
        mock_engine_fn,
        mock_cache_fn,
        mock_cache_reasoning_fn,
        mock_save_bundle,
        mock_gen_reasoning,
        mock_get_settings,
    ):
        self._setup_fresh_prediction(mock_engine_fn, mock_cache_fn)
        mock_save_bundle.return_value = []
        mock_cache_reasoning_fn.return_value = None

        # Force agent-loop path for this test.
        mock_settings = MagicMock()
        mock_settings.use_single_shot_reasoning = False
        mock_get_settings.return_value = mock_settings

        # Agent blows up.
        mock_gen_reasoning.side_effect = RuntimeError("Anthropic API down")

        async with AsyncClient(
            transport=ASGITransport(app=_app), base_url="http://test"
        ) as ac:
            resp = await ac.get("/api/football/predict/pre-match/100")

        assert resp.status_code == 200
        body = resp.json()
        # Deterministic prediction is present.
        assert "predictions" in body
        assert body["cached"] is False
        # Reasoning failed gracefully.
        assert body["reasoning"] is None
        assert body["upset"] is None
        # Deterministic save + commit still happened (commit before reasoning).
        mock_save_bundle.assert_awaited_once()
        self.mock_session.commit.assert_awaited()
        # Only one commit — the reasoning commit never happened.
        assert self.mock_session.commit.await_count == 1

    @patch("backend.football.routes.generate_reasoning")
    @patch("backend.football.routes.save_prediction_bundle")
    @patch("backend.football.routes.get_cached_reasoning")
    @patch("backend.football.routes.get_cached_bundle")
    @patch("backend.football.routes._get_engine")
    async def test_reasoning_cached_skips_agent(
        self,
        mock_engine_fn,
        mock_cache_fn,
        mock_cache_reasoning_fn,
        mock_save_bundle,
        mock_gen_reasoning,
    ):
        self._setup_fresh_prediction(mock_engine_fn, mock_cache_fn)
        mock_save_bundle.return_value = []

        # Reasoning cache hit.
        cached_reasoning_row = _make_prediction_row(
            prediction_type="reasoning"
        )
        cached_reasoning_row.payload = {
            "paragraphs": ["Cached P1.", "Cached P2.", "Cached P3."],
            "claims": [],
            "upset_signals": [],
            "upset_paths": [],
            "validation_status": "valid",
        }
        cached_upset_row = _make_prediction_row(
            prediction_type="upset_index"
        )
        cached_upset_row.payload = {
            "upset_index": 0.30,
            "deterministic_component": 0.20,
            "agent_component": 0.40,
            "bounded_agent": 0.35,
            "upset_signals": [],
            "upset_paths": [],
        }
        mock_cache_reasoning_fn.return_value = {
            "reasoning": cached_reasoning_row,
            "upset_index": cached_upset_row,
        }

        async with AsyncClient(
            transport=ASGITransport(app=_app), base_url="http://test"
        ) as ac:
            resp = await ac.get("/api/football/predict/pre-match/100")

        assert resp.status_code == 200
        body = resp.json()
        assert body["reasoning"]["paragraphs"][0] == "Cached P1."
        assert body["upset"]["upset_index"] == 0.30
        # Agent was NOT called.
        mock_gen_reasoning.assert_not_awaited()

    @patch("backend.football.routes.save_prediction_bundle")
    @patch("backend.football.routes.get_cached_bundle")
    @patch("backend.football.routes._get_engine")
    async def test_no_anthropic_key_returns_null_reasoning(
        self,
        mock_engine_fn,
        mock_cache_fn,
        mock_save_bundle,
    ):
        """When agent_client is None, reasoning is skipped cleanly."""
        # Override agent to return None.
        from backend.football.deps import get_agent_client

        _app.dependency_overrides[get_agent_client] = lambda: None

        self._setup_fresh_prediction(mock_engine_fn, mock_cache_fn)
        mock_save_bundle.return_value = []

        async with AsyncClient(
            transport=ASGITransport(app=_app), base_url="http://test"
        ) as ac:
            resp = await ac.get("/api/football/predict/pre-match/100")

        assert resp.status_code == 200
        body = resp.json()
        assert body["reasoning"] is None
        assert body["upset"] is None


# ── Reasoning endpoint tests ────────────────────────────────────────


class TestGetReasoning:
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

    @patch("backend.football.routes.get_latest_reasoning")
    async def test_reasoning_exists(self, mock_get):
        row = _make_prediction_row(prediction_type="reasoning")
        row.payload = {
            "paragraphs": ["P1.", "P2.", "P3."],
            "claims": [],
            "upset_signals": [],
            "upset_paths": [],
            "validation_status": "valid",
        }
        mock_get.return_value = row

        async with AsyncClient(
            transport=ASGITransport(app=_app), base_url="http://test"
        ) as ac:
            resp = await ac.get("/api/football/predict/reasoning/100")

        assert resp.status_code == 200
        body = resp.json()
        assert body["fixture_id"] == 100
        assert body["prediction_type"] == "reasoning"
        assert body["payload"]["paragraphs"] == ["P1.", "P2.", "P3."]

    @patch("backend.football.routes.get_latest_reasoning")
    async def test_reasoning_missing_returns_503(self, mock_get):
        mock_get.return_value = None

        async with AsyncClient(
            transport=ASGITransport(app=_app), base_url="http://test"
        ) as ac:
            resp = await ac.get("/api/football/predict/reasoning/999")

        assert resp.status_code == 503


# ── Upset persistence tests ─────────────────────────────────────────


class TestUpsetPersistence:
    @pytest.mark.asyncio
    async def test_upset_row_has_decimal_index(self):
        """Verify save_upset_output sets Prediction.upset_index as Decimal."""
        from decimal import Decimal
        from unittest.mock import AsyncMock

        from backend.football.persistence import save_upset_output

        mock_session = AsyncMock()

        # Build a minimal UpsetOutput-like object.
        mock_upset = MagicMock()
        mock_upset.upset_index = 0.277
        mock_upset.deterministic_component = 0.217
        mock_upset.agent_component = 0.40
        mock_upset.bounded_agent = 0.367
        mock_upset.upset_signals = []
        mock_upset.upset_paths = []

        row = await save_upset_output(
            mock_session, fixture_id=100, upset_output=mock_upset,
            stage="pre_lineup",
        )

        assert row.prediction_type == "upset_index"
        assert row.model_version == "hybrid_v1"
        assert isinstance(row.upset_index, Decimal)
        assert row.upset_index == Decimal("0.28")


# ── Upset watch endpoint ────────────────────────────────────────────


def _make_upset_prediction_row(
    fixture_id: int = 100,
    upset_index_value: float = 0.50,
    upset_paths: list[str] | None = None,
) -> Prediction:
    """Build a Prediction row with prediction_type='upset_index'."""
    row = Prediction()
    row.id = uuid.uuid4()
    row.fixture_id = fixture_id
    row.prediction_type = "upset_index"
    row.stage = "pre_lineup"
    row.made_at = datetime.now(timezone.utc)
    row.payload = {
        "upset_index": upset_index_value,
        "deterministic_component": 0.30,
        "agent_component": 0.40,
        "bounded_agent": 0.37,
        "upset_signals": [],
        "upset_paths": upset_paths or [
            "Path 1",
            "Path 2",
            "Path 3",
        ],
    }
    row.model_version = "hybrid_v1"
    row.upset_index = Decimal(str(round(upset_index_value, 2)))
    row.confidence = None
    return row


class TestListUpsets:
    @pytest.fixture(autouse=True)
    def _setup_deps(self):
        self.mock_client = AsyncMock()
        self.mock_session = AsyncMock()

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

    @patch("backend.football.routes.get_upsets_above_threshold")
    async def test_empty_db_returns_empty_list(self, mock_get_upsets):
        mock_get_upsets.return_value = []

        async with AsyncClient(
            transport=ASGITransport(app=_app), base_url="http://test"
        ) as ac:
            resp = await ac.get("/api/football/upsets")

        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 0
        assert body["threshold"] == 0.45
        assert body["upsets"] == []

    @patch("backend.football.routes.get_upsets_above_threshold")
    async def test_single_qualifying_fixture(self, mock_get_upsets):
        pred = _make_upset_prediction_row(
            fixture_id=100, upset_index_value=0.54
        )
        mock_get_upsets.return_value = [pred]

        fx = _make_fixture(
            fixture_id=100,
            home_name="Mexico",
            away_name="South Africa",
        )
        self.mock_client.get_fixtures = AsyncMock(return_value=[fx])

        async with AsyncClient(
            transport=ASGITransport(app=_app), base_url="http://test"
        ) as ac:
            resp = await ac.get("/api/football/upsets")

        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 1
        item = body["upsets"][0]
        assert item["fixture_id"] == 100
        assert item["home_team"] == "Mexico"
        assert item["away_team"] == "South Africa"
        assert item["upset_index"] == 0.54
        assert item["upset_paths"] == ["Path 1", "Path 2", "Path 3"]
        assert item["status"] == "NS"
        assert item["round"] == "Group A - 1"
        assert "kickoff" in item

    @patch("backend.football.routes.get_upsets_above_threshold")
    async def test_multiple_fixtures_preserve_sort_order(
        self, mock_get_upsets
    ):
        # Persistence returns sorted by upset_index DESC.
        pred_high = _make_upset_prediction_row(
            fixture_id=200, upset_index_value=0.62
        )
        pred_low = _make_upset_prediction_row(
            fixture_id=100, upset_index_value=0.48
        )
        mock_get_upsets.return_value = [pred_high, pred_low]

        fx1 = _make_fixture(fixture_id=100, home_name="Brazil")
        fx2 = _make_fixture(fixture_id=200, home_name="Germany")
        self.mock_client.get_fixtures = AsyncMock(
            return_value=[fx1, fx2]
        )

        async with AsyncClient(
            transport=ASGITransport(app=_app), base_url="http://test"
        ) as ac:
            resp = await ac.get("/api/football/upsets")

        body = resp.json()
        assert body["count"] == 2
        assert body["upsets"][0]["upset_index"] == 0.62
        assert body["upsets"][1]["upset_index"] == 0.48

    @patch("backend.football.routes.get_upsets_above_threshold")
    async def test_excludes_finished_fixtures(self, mock_get_upsets):
        pred = _make_upset_prediction_row(
            fixture_id=100, upset_index_value=0.55
        )
        mock_get_upsets.return_value = [pred]

        fx = _make_fixture(
            fixture_id=100,
            status_short="FT",
            status_long="Match Finished",
        )
        self.mock_client.get_fixtures = AsyncMock(return_value=[fx])

        async with AsyncClient(
            transport=ASGITransport(app=_app), base_url="http://test"
        ) as ac:
            resp = await ac.get("/api/football/upsets")

        body = resp.json()
        assert body["count"] == 0
        assert body["upsets"] == []

    @patch("backend.football.routes.get_upsets_above_threshold")
    async def test_custom_threshold_via_query_param(
        self, mock_get_upsets
    ):
        mock_get_upsets.return_value = []

        async with AsyncClient(
            transport=ASGITransport(app=_app), base_url="http://test"
        ) as ac:
            resp = await ac.get(
                "/api/football/upsets?threshold=0.6"
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["threshold"] == 0.6
        mock_get_upsets.assert_awaited_once_with(
            self.mock_session, 0.6
        )

    @patch("backend.football.routes.get_upsets_above_threshold")
    async def test_fixture_not_in_api_is_skipped(self, mock_get_upsets):
        # Prediction for fixture 999, but API-Football only knows 100.
        pred = _make_upset_prediction_row(
            fixture_id=999, upset_index_value=0.50
        )
        mock_get_upsets.return_value = [pred]

        fx = _make_fixture(fixture_id=100)
        self.mock_client.get_fixtures = AsyncMock(return_value=[fx])

        async with AsyncClient(
            transport=ASGITransport(app=_app), base_url="http://test"
        ) as ac:
            resp = await ac.get("/api/football/upsets")

        body = resp.json()
        assert body["count"] == 0
        assert body["upsets"] == []

    @patch("backend.football.routes.get_upsets_above_threshold")
    async def test_api_football_failure_returns_error(
        self, mock_get_upsets
    ):
        from backend.football.exceptions import UpstreamError

        pred = _make_upset_prediction_row(fixture_id=100)
        mock_get_upsets.return_value = [pred]
        self.mock_client.get_fixtures = AsyncMock(
            side_effect=UpstreamError("API down")
        )

        async with AsyncClient(
            transport=ASGITransport(app=_app), base_url="http://test"
        ) as ac:
            resp = await ac.get("/api/football/upsets")

        assert resp.status_code == 503

    @patch("backend.football.routes.get_upsets_above_threshold")
    async def test_default_threshold_is_045(self, mock_get_upsets):
        mock_get_upsets.return_value = []

        async with AsyncClient(
            transport=ASGITransport(app=_app), base_url="http://test"
        ) as ac:
            resp = await ac.get("/api/football/upsets")

        assert resp.status_code == 200
        mock_get_upsets.assert_awaited_once_with(
            self.mock_session, 0.45
        )


# ── Single-shot feature flag tests ────────────────────────────────


class TestSingleShotFeatureFlag:
    """Verify USE_SINGLE_SHOT_REASONING flag routes to the correct path."""

    @pytest.fixture(autouse=True)
    def _setup_deps(self):
        self.mock_client = AsyncMock()
        self.mock_session = AsyncMock()
        self.mock_session.commit = AsyncMock()
        self.mock_agent = MagicMock()

        async def _override_client():
            return self.mock_client

        async def _override_session():
            return self.mock_session

        def _override_agent():
            return self.mock_agent

        _app.dependency_overrides.clear()
        from backend.football.deps import get_agent_client, get_football_client
        from backend.shared.db import get_session

        _app.dependency_overrides[get_football_client] = _override_client
        _app.dependency_overrides[get_session] = _override_session
        _app.dependency_overrides[get_agent_client] = _override_agent

        yield
        _app.dependency_overrides.clear()

    def _setup_fresh_prediction(self, mock_engine_fn, mock_cache_fn):
        """Common setup: NS fixture, no cache, mock engine."""
        fx = _make_fixture()
        self.mock_client.get_fixture = AsyncMock(return_value=fx)
        self.mock_client.get_lineups = AsyncMock(return_value=[])
        mock_cache_fn.return_value = None

        mock_engine = MagicMock()
        mock_bundle = MagicMock()
        mock_bundle.stage.value = "pre_lineup"
        mock_bundle.model_version = "dixon_coles_v1"
        mock_bundle.confidence = "normal"
        mock_bundle.winner.model_dump.return_value = {"p_home_win": 0.4}
        mock_bundle.total_goals.model_dump.return_value = {"over_2_5": 0.5}
        mock_bundle.ht_score.model_dump.return_value = {"p_draw": 0.3}
        mock_bundle.first_to_score.model_dump.return_value = {
            "p_home_first": 0.5
        }
        mock_engine.predict.return_value = mock_bundle
        mock_engine_fn.return_value = mock_engine
        return mock_bundle

    def _mock_reasoning_output(self):
        """Build a mock ReasoningOutput for both paths."""
        mock_reasoning = MagicMock()
        mock_reasoning.paragraphs = ["P1.", "P2.", "P3."]
        mock_reasoning.claims = []
        mock_reasoning.upset_index = 0.40
        mock_reasoning.upset_signals = []
        mock_reasoning.upset_paths = []
        mock_reasoning.validation_status = "valid"
        mock_cost = MagicMock()
        mock_cost.input_tokens = 100
        mock_cost.output_tokens = 50
        mock_cost.cache_creation_input_tokens = 0
        mock_cost.cache_read_input_tokens = 0
        return mock_reasoning, mock_cost

    def _mock_upset_output(self):
        """Build a mock UpsetOutput."""
        mock_upset = MagicMock()
        mock_upset.upset_index = 0.28
        mock_upset.deterministic_component = 0.22
        mock_upset.agent_component = 0.40
        mock_upset.bounded_agent = 0.37
        mock_upset.upset_signals = []
        mock_upset.upset_paths = []
        return mock_upset

    @patch("backend.football.routes.get_settings")
    @patch("backend.football.routes.compute_upset_index")
    @patch("backend.football.routes.generate_reasoning_single_shot")
    @patch("backend.football.routes.pre_fetch_match_context")
    @patch("backend.football.routes.generate_reasoning")
    @patch("backend.football.routes.save_upset_output")
    @patch("backend.football.routes.save_reasoning_output")
    @patch("backend.football.routes.save_prediction_bundle")
    @patch("backend.football.routes.get_cached_reasoning")
    @patch("backend.football.routes.get_cached_bundle")
    @patch("backend.football.routes._get_engine")
    async def test_flag_on_calls_single_shot_path(
        self,
        mock_engine_fn,
        mock_cache_fn,
        mock_cache_reasoning_fn,
        mock_save_bundle,
        mock_save_reasoning,
        mock_save_upset,
        mock_gen_reasoning,
        mock_prefetch,
        mock_gen_single_shot,
        mock_compute_upset,
        mock_get_settings,
    ):
        """Flag ON: pre_fetch + single_shot called; agent loop NOT called."""
        self._setup_fresh_prediction(mock_engine_fn, mock_cache_fn)
        mock_save_bundle.return_value = []
        mock_cache_reasoning_fn.return_value = None

        # Configure settings mock: flag ON.
        mock_settings = MagicMock()
        mock_settings.use_single_shot_reasoning = True
        mock_get_settings.return_value = mock_settings

        # Mock pre-fetch.
        mock_ctx = MagicMock()
        mock_prefetch.return_value = mock_ctx

        # Mock single-shot reasoning.
        mock_reasoning, mock_cost = self._mock_reasoning_output()
        mock_gen_single_shot.return_value = (mock_reasoning, mock_cost)

        # Mock upset.
        mock_compute_upset.return_value = self._mock_upset_output()
        mock_save_reasoning.return_value = MagicMock()
        mock_save_upset.return_value = MagicMock()

        async with AsyncClient(
            transport=ASGITransport(app=_app), base_url="http://test"
        ) as ac:
            resp = await ac.get("/api/football/predict/pre-match/100")

        assert resp.status_code == 200
        body = resp.json()

        # Single-shot path was called.
        mock_prefetch.assert_awaited_once()
        mock_gen_single_shot.assert_awaited_once()

        # Agent loop was NOT called.
        mock_gen_reasoning.assert_not_awaited()

        # Response has reasoning.
        assert body["reasoning"] is not None
        assert body["reasoning"]["paragraphs"] == ["P1.", "P2.", "P3."]

    @patch("backend.football.routes.get_settings")
    @patch("backend.football.routes.compute_upset_index")
    @patch("backend.football.routes.generate_reasoning_single_shot")
    @patch("backend.football.routes.pre_fetch_match_context")
    @patch("backend.football.routes.generate_reasoning")
    @patch("backend.football.routes.save_upset_output")
    @patch("backend.football.routes.save_reasoning_output")
    @patch("backend.football.routes.save_prediction_bundle")
    @patch("backend.football.routes.get_cached_reasoning")
    @patch("backend.football.routes.get_cached_bundle")
    @patch("backend.football.routes._get_engine")
    async def test_flag_off_calls_agent_loop(
        self,
        mock_engine_fn,
        mock_cache_fn,
        mock_cache_reasoning_fn,
        mock_save_bundle,
        mock_save_reasoning,
        mock_save_upset,
        mock_gen_reasoning,
        mock_prefetch,
        mock_gen_single_shot,
        mock_compute_upset,
        mock_get_settings,
    ):
        """Flag OFF: agent loop called; pre_fetch + single_shot NOT called."""
        self._setup_fresh_prediction(mock_engine_fn, mock_cache_fn)
        mock_save_bundle.return_value = []
        mock_cache_reasoning_fn.return_value = None

        # Configure settings mock: flag OFF.
        mock_settings = MagicMock()
        mock_settings.use_single_shot_reasoning = False
        mock_get_settings.return_value = mock_settings

        # Mock agent loop reasoning.
        mock_reasoning, mock_cost = self._mock_reasoning_output()
        mock_gen_reasoning.return_value = (mock_reasoning, mock_cost)

        # Mock upset.
        mock_compute_upset.return_value = self._mock_upset_output()
        mock_save_reasoning.return_value = MagicMock()
        mock_save_upset.return_value = MagicMock()

        async with AsyncClient(
            transport=ASGITransport(app=_app), base_url="http://test"
        ) as ac:
            resp = await ac.get("/api/football/predict/pre-match/100")

        assert resp.status_code == 200
        body = resp.json()

        # Agent loop was called.
        mock_gen_reasoning.assert_awaited_once()

        # Single-shot path was NOT called.
        mock_prefetch.assert_not_awaited()
        mock_gen_single_shot.assert_not_awaited()

        # Response has reasoning.
        assert body["reasoning"] is not None
        assert body["reasoning"]["paragraphs"] == ["P1.", "P2.", "P3."]

    @patch("backend.football.routes.get_settings")
    @patch("backend.football.routes.compute_upset_index")
    @patch("backend.football.routes.generate_reasoning_single_shot")
    @patch("backend.football.routes.pre_fetch_match_context")
    @patch("backend.football.routes.generate_reasoning")
    @patch("backend.football.routes.save_upset_output")
    @patch("backend.football.routes.save_reasoning_output")
    @patch("backend.football.routes.save_prediction_bundle")
    @patch("backend.football.routes.get_cached_reasoning")
    @patch("backend.football.routes.get_cached_bundle")
    @patch("backend.football.routes._get_engine")
    async def test_both_flags_produce_equivalent_response_shape(
        self,
        mock_engine_fn,
        mock_cache_fn,
        mock_cache_reasoning_fn,
        mock_save_bundle,
        mock_save_reasoning,
        mock_save_upset,
        mock_gen_reasoning,
        mock_prefetch,
        mock_gen_single_shot,
        mock_compute_upset,
        mock_get_settings,
    ):
        """Both flag states produce structurally equivalent JSON responses."""
        responses = {}

        for flag_value in (True, False):
            self._setup_fresh_prediction(mock_engine_fn, mock_cache_fn)
            mock_save_bundle.return_value = []
            mock_cache_reasoning_fn.return_value = None

            mock_settings = MagicMock()
            mock_settings.use_single_shot_reasoning = flag_value
            mock_get_settings.return_value = mock_settings

            mock_reasoning, mock_cost = self._mock_reasoning_output()

            if flag_value:
                mock_ctx = MagicMock()
                mock_prefetch.return_value = mock_ctx
                mock_gen_single_shot.return_value = (
                    mock_reasoning,
                    mock_cost,
                )
            else:
                mock_gen_reasoning.return_value = (
                    mock_reasoning,
                    mock_cost,
                )

            mock_compute_upset.return_value = self._mock_upset_output()
            mock_save_reasoning.return_value = MagicMock()
            mock_save_upset.return_value = MagicMock()

            # Reset commit mock for clean count.
            self.mock_session.commit.reset_mock()

            async with AsyncClient(
                transport=ASGITransport(app=_app), base_url="http://test"
            ) as ac:
                resp = await ac.get(
                    "/api/football/predict/pre-match/100"
                )

            assert resp.status_code == 200
            responses[flag_value] = resp.json()

        # Both responses have the same top-level keys.
        assert set(responses[True].keys()) == set(responses[False].keys())

        # Both have identical structure for key fields.
        for key in (
            "fixture_id",
            "home_team",
            "away_team",
            "status",
            "stage",
            "cached",
        ):
            assert responses[True][key] == responses[False][key]

        # Both have reasoning and upset payloads.
        assert responses[True]["reasoning"] is not None
        assert responses[False]["reasoning"] is not None
        assert responses[True]["upset"] is not None
        assert responses[False]["upset"] is not None

        # Both reasoning payloads have the same keys.
        assert set(responses[True]["reasoning"].keys()) == set(
            responses[False]["reasoning"].keys()
        )


# ── Rounds endpoint ─────────────────────────────────────────────────


class TestListRounds:
    @pytest.fixture(autouse=True)
    def _setup_deps(self):
        self.mock_client = AsyncMock()

        async def _override_client():
            return self.mock_client

        _app.dependency_overrides.clear()
        from backend.football.deps import get_football_client

        _app.dependency_overrides[get_football_client] = _override_client

        yield
        _app.dependency_overrides.clear()

    async def test_returns_rounds_with_expected_shape(self):
        self.mock_client.get_rounds = AsyncMock(
            return_value=[
                "Group A - 1",
                "Group A - 2",
                "Group A - 3",
                "Round of 32",
                "Round of 16",
                "Quarter-finals",
                "Semi-finals",
                "3rd Place Final",
                "Final",
            ]
        )

        async with AsyncClient(
            transport=ASGITransport(app=_app), base_url="http://test"
        ) as ac:
            resp = await ac.get("/api/football/fixtures/rounds")

        assert resp.status_code == 200
        data = resp.json()
        assert "count" in data
        assert "rounds" in data
        assert data["count"] == 9
        assert isinstance(data["rounds"], list)
        assert data["rounds"][0] == "Group A - 1"
        assert data["rounds"][-1] == "Final"

    async def test_cache_control_header_set(self):
        self.mock_client.get_rounds = AsyncMock(return_value=["Group A - 1"])

        async with AsyncClient(
            transport=ASGITransport(app=_app), base_url="http://test"
        ) as ac:
            resp = await ac.get("/api/football/fixtures/rounds")

        assert resp.status_code == 200
        assert "max-age=300" in resp.headers.get("cache-control", "")

    async def test_upstream_error_returns_503(self):
        from backend.football.exceptions import UpstreamError

        self.mock_client.get_rounds = AsyncMock(
            side_effect=UpstreamError(status_code=500)
        )

        async with AsyncClient(
            transport=ASGITransport(app=_app), base_url="http://test"
        ) as ac:
            resp = await ac.get("/api/football/fixtures/rounds")

        assert resp.status_code == 503

    async def test_empty_rounds_returns_zero_count(self):
        self.mock_client.get_rounds = AsyncMock(return_value=[])

        async with AsyncClient(
            transport=ASGITransport(app=_app), base_url="http://test"
        ) as ac:
            resp = await ac.get("/api/football/fixtures/rounds")

        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 0
        assert data["rounds"] == []


# ── Standings endpoint ───────────────────────────────────────────────


def _make_standings_response():
    """Build a minimal AFStandingsResponse for route tests."""
    from backend.football.schemas import (
        AFStandingEntry,
        AFStandingGoals,
        AFStandingStats,
        AFStandingsLeague,
        AFStandingsResponse,
        AFStandingTeam,
    )

    def _team(tid: int, name: str) -> AFStandingTeam:
        return AFStandingTeam(id=tid, name=name, logo=None)

    def _stats(
        played: int = 0, win: int = 0, draw: int = 0, lose: int = 0,
        gf: int = 0, ga: int = 0,
    ) -> AFStandingStats:
        return AFStandingStats(
            played=played, win=win, draw=draw, lose=lose,
            goals=AFStandingGoals(goals_for=gf, against=ga),
        )

    group_a = [
        AFStandingEntry(
            rank=1, team=_team(10, "France"), points=0, goalsDiff=0,
            group="Group A", all=_stats(),
        ),
        AFStandingEntry(
            rank=2, team=_team(20, "Argentina"), points=0, goalsDiff=0,
            group="Group A", all=_stats(),
        ),
    ]

    return AFStandingsResponse(
        league=AFStandingsLeague(
            id=1, name="World Cup", season=2026,
            standings=[group_a],
        )
    )


class TestGetStandings:
    @pytest.fixture(autouse=True)
    def _setup_deps(self):
        self.mock_client = AsyncMock()

        async def _override_client():
            return self.mock_client

        _app.dependency_overrides.clear()
        from backend.football.deps import get_football_client

        _app.dependency_overrides[get_football_client] = _override_client

        yield
        _app.dependency_overrides.clear()

    async def test_returns_standings_with_expected_shape(self):
        self.mock_client.get_standings = AsyncMock(
            return_value=_make_standings_response()
        )

        async with AsyncClient(
            transport=ASGITransport(app=_app), base_url="http://test"
        ) as ac:
            resp = await ac.get("/api/football/standings")

        assert resp.status_code == 200
        data = resp.json()
        assert "league" in data
        league = data["league"]
        assert league["id"] == 1
        assert league["name"] == "World Cup"
        assert league["season"] == 2026
        assert isinstance(league["standings"], list)
        assert len(league["standings"]) == 1
        group = league["standings"][0]
        assert len(group) == 2
        assert group[0]["team"]["name"] == "France"
        assert group[0]["rank"] == 1
        assert group[1]["team"]["name"] == "Argentina"

    async def test_cache_control_header_60s(self):
        self.mock_client.get_standings = AsyncMock(
            return_value=_make_standings_response()
        )

        async with AsyncClient(
            transport=ASGITransport(app=_app), base_url="http://test"
        ) as ac:
            resp = await ac.get("/api/football/standings")

        assert resp.status_code == 200
        assert "max-age=60" in resp.headers.get("cache-control", "")

    async def test_upstream_error_returns_503(self):
        from backend.football.exceptions import UpstreamError

        self.mock_client.get_standings = AsyncMock(
            side_effect=UpstreamError(status_code=500)
        )

        async with AsyncClient(
            transport=ASGITransport(app=_app), base_url="http://test"
        ) as ac:
            resp = await ac.get("/api/football/standings")

        assert resp.status_code == 503

    async def test_none_standings_returns_empty(self):
        self.mock_client.get_standings = AsyncMock(return_value=None)

        async with AsyncClient(
            transport=ASGITransport(app=_app), base_url="http://test"
        ) as ac:
            resp = await ac.get("/api/football/standings")

        assert resp.status_code == 200
        data = resp.json()
        assert data["league"] is None
        assert data["groups"] == []

    async def test_goals_serialised_with_for_alias(self):
        self.mock_client.get_standings = AsyncMock(
            return_value=_make_standings_response()
        )

        async with AsyncClient(
            transport=ASGITransport(app=_app), base_url="http://test"
        ) as ac:
            resp = await ac.get("/api/football/standings")

        data = resp.json()
        entry = data["league"]["standings"][0][0]
        goals = entry["all"]["goals"]
        # Must use the "for" alias, not "goals_for"
        assert "for" in goals
        assert "against" in goals


# ── Head-to-Head route tests ────────────────────────────────────────────


class TestGetHeadToHead:
    """Tests for GET /api/football/head-to-head."""

    @pytest.fixture(autouse=True)
    def _setup_deps(self):
        self.mock_client = AsyncMock()

        async def _override_client():
            return self.mock_client

        _app.dependency_overrides.clear()
        from backend.football.deps import get_football_client

        _app.dependency_overrides[get_football_client] = _override_client

        yield
        _app.dependency_overrides.clear()

    async def test_response_shape_with_fixtures(self):
        """Returns fixtures, summary, and correct structure."""
        h2h_fixtures = [
            _make_fixture(
                fixture_id=1, home_id=10, away_id=20,
                home_name="Brazil", away_name="Germany",
                home_goals=2, away_goals=1,
                status_short="FT", status_long="Match Finished",
            ),
            _make_fixture(
                fixture_id=2, home_id=20, away_id=10,
                home_name="Germany", away_name="Brazil",
                home_goals=0, away_goals=0,
                status_short="FT", status_long="Match Finished",
            ),
            _make_fixture(
                fixture_id=3, home_id=10, away_id=20,
                home_name="Brazil", away_name="Germany",
                home_goals=1, away_goals=3,
                status_short="FT", status_long="Match Finished",
            ),
        ]
        self.mock_client.get_head_to_head = AsyncMock(return_value=h2h_fixtures)

        async with AsyncClient(
            transport=ASGITransport(app=_app), base_url="http://test"
        ) as ac:
            resp = await ac.get(
                "/api/football/head-to-head",
                params={"team1": 10, "team2": 20, "last": 5},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["team1_id"] == 10
        assert data["team2_id"] == 20
        assert data["count"] == 3
        assert len(data["fixtures"]) == 3
        # Summary from team1 (id=10 = Brazil) perspective:
        # Fixture 1: Brazil 2-1 Germany → win
        # Fixture 2: Germany 0-0 Brazil → draw
        # Fixture 3: Brazil 1-3 Germany → loss
        assert data["summary"] == {"wins": 1, "draws": 1, "losses": 1}

    async def test_cache_header_1h(self):
        """Cache-Control should be 3600s (1 hour)."""
        self.mock_client.get_head_to_head = AsyncMock(return_value=[])

        async with AsyncClient(
            transport=ASGITransport(app=_app), base_url="http://test"
        ) as ac:
            resp = await ac.get(
                "/api/football/head-to-head",
                params={"team1": 10, "team2": 20},
            )

        assert resp.status_code == 200
        assert "max-age=3600" in resp.headers.get("cache-control", "")

    async def test_empty_result(self):
        """No previous meetings returns empty fixtures and zero summary."""
        self.mock_client.get_head_to_head = AsyncMock(return_value=[])

        async with AsyncClient(
            transport=ASGITransport(app=_app), base_url="http://test"
        ) as ac:
            resp = await ac.get(
                "/api/football/head-to-head",
                params={"team1": 10, "team2": 20},
            )

        data = resp.json()
        assert data["count"] == 0
        assert data["fixtures"] == []
        assert data["summary"] == {"wins": 0, "draws": 0, "losses": 0}

    async def test_upstream_error_returns_503(self):
        """Upstream errors translate to 503."""
        from backend.football.exceptions import UpstreamError

        self.mock_client.get_head_to_head = AsyncMock(
            side_effect=UpstreamError("timeout")
        )

        async with AsyncClient(
            transport=ASGITransport(app=_app), base_url="http://test"
        ) as ac:
            resp = await ac.get(
                "/api/football/head-to-head",
                params={"team1": 10, "team2": 20},
            )

        assert resp.status_code == 503

    async def test_summary_team1_away_win(self):
        """When team1 is the away side and wins, summary counts it correctly."""
        # team1=10, but in this fixture team1 is AWAY and wins 3-1
        h2h_fixtures = [
            _make_fixture(
                fixture_id=5, home_id=20, away_id=10,
                home_name="Germany", away_name="Brazil",
                home_goals=1, away_goals=3,
                status_short="FT", status_long="Match Finished",
            ),
        ]
        self.mock_client.get_head_to_head = AsyncMock(return_value=h2h_fixtures)

        async with AsyncClient(
            transport=ASGITransport(app=_app), base_url="http://test"
        ) as ac:
            resp = await ac.get(
                "/api/football/head-to-head",
                params={"team1": 10, "team2": 20},
            )

        data = resp.json()
        assert data["summary"] == {"wins": 1, "draws": 0, "losses": 0}

    async def test_missing_team_params_returns_422(self):
        """Omitting required team1/team2 params returns 422."""
        async with AsyncClient(
            transport=ASGITransport(app=_app), base_url="http://test"
        ) as ac:
            resp = await ac.get("/api/football/head-to-head")

        assert resp.status_code == 422
