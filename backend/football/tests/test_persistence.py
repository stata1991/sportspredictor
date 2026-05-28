"""Tests for the football persistence layer (5.2.3).

Uses mock AsyncSession objects — does NOT write to the real ``football.*``
tables.  JSONB round-trip correctness is verified via pure Pydantic
serialisation tests (no DB needed).

Test approach
-------------
- **save functions**: mock ``session.add_all`` / ``session.execute`` /
  ``session.flush`` and assert the right ORM objects are produced.
- **get functions**: configure ``session.execute`` to return mock result
  sets and verify the return values.
- **append-only**: confirm that ``save_prediction_bundle`` only calls
  ``add_all`` (INSERT), never ``execute`` with an UPDATE.
- **JSONB round-trip**: verify each payload model survives
  ``model_dump(mode='json') → model_validate()``.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from backend.football.models.dixon_coles import DixonColesModel
from backend.football.persistence import (
    CACHE_MAX_AGE_SECONDS,
    LIVE_CACHE_MAX_AGE_SECONDS,
    PREDICTION_TYPES,
    get_all_accuracy_rollups,
    get_cached_bundle,
    get_cached_live_prediction,
    get_latest_predictions_for_fixture,
    get_outcome,
    get_predictions_for_fixture,
    save_live_prediction,
    save_outcome,
    save_prediction_bundle,
)
from backend.football.predictions.engine import PredictionEngine
from backend.football.predictions.schemas import (
    FirstToScorePayload,
    FixtureStage,
    HTScorePayload,
    PredictionBundle,
    TotalGoalsPayload,
    WinnerPayload,
)
from backend.shared.models import AccuracyRollup, Outcome, Prediction


# ── Helpers ──────────────────────────────────────────────────────────


def _make_model() -> DixonColesModel:
    """Minimal 2-team model for generating realistic bundles."""
    return DixonColesModel(
        attack={1: 0.2, 2: -0.2},
        defence={1: -0.1, 2: 0.1},
        gamma=0.25,
        rho=-0.05,
        xi=0.0065,
        training_matches=100,
        training_window="2023-01-01 to 2024-01-01",
        team_names={1: "Home FC", 2: "Away United"},
    )


@pytest.fixture
def bundle(tmp_path) -> PredictionBundle:
    """A real PredictionBundle from the engine (synthetic model)."""
    model = _make_model()
    model_path = tmp_path / "test_model.json"
    model.save(model_path)
    engine = PredictionEngine(model_path=model_path)
    return engine.predict(1, 2, "NS")


@pytest.fixture
def mock_session() -> AsyncMock:
    """AsyncMock that behaves like an AsyncSession."""
    session = AsyncMock()
    session.add_all = MagicMock()  # sync method, not awaitable
    return session


def _make_prediction_row(
    fixture_id: int = 100,
    prediction_type: str = "winner",
    stage: str = "pre_lineup",
    made_at: datetime | None = None,
) -> Prediction:
    """Create a Prediction ORM instance for mock return values."""
    row = Prediction()
    row.id = uuid.uuid4()
    row.fixture_id = fixture_id
    row.prediction_type = prediction_type
    row.stage = stage
    row.made_at = made_at or datetime.now(timezone.utc)
    row.payload = {"test": True}
    row.model_version = "dixon_coles_v1"
    row.upset_index = None
    row.confidence = None
    return row


# ── save_prediction_bundle ───────────────────────────────────────────


class TestSavePredictionBundle:
    async def test_creates_four_rows(self, mock_session, bundle):
        rows = await save_prediction_bundle(mock_session, 100, bundle)
        assert len(rows) == 4

    async def test_all_rows_are_prediction_instances(self, mock_session, bundle):
        rows = await save_prediction_bundle(mock_session, 100, bundle)
        assert all(isinstance(r, Prediction) for r in rows)

    async def test_prediction_types_match(self, mock_session, bundle):
        rows = await save_prediction_bundle(mock_session, 100, bundle)
        types = {r.prediction_type for r in rows}
        assert types == set(PREDICTION_TYPES)

    async def test_fixture_id_set_on_all_rows(self, mock_session, bundle):
        rows = await save_prediction_bundle(mock_session, 100, bundle)
        assert all(r.fixture_id == 100 for r in rows)

    async def test_stage_stored_as_string(self, mock_session, bundle):
        rows = await save_prediction_bundle(mock_session, 100, bundle)
        assert all(r.stage == "pre_lineup" for r in rows)

    async def test_model_version_set(self, mock_session, bundle):
        rows = await save_prediction_bundle(mock_session, 100, bundle)
        assert all(r.model_version == "dixon_coles_v1" for r in rows)

    async def test_payloads_are_dicts(self, mock_session, bundle):
        rows = await save_prediction_bundle(mock_session, 100, bundle)
        assert all(isinstance(r.payload, dict) for r in rows)

    async def test_winner_payload_has_scoreline_matrix(self, mock_session, bundle):
        rows = await save_prediction_bundle(mock_session, 100, bundle)
        winner_row = next(r for r in rows if r.prediction_type == "winner")
        assert "scoreline_matrix" in winner_row.payload
        assert len(winner_row.payload["scoreline_matrix"]) == 8

    async def test_ht_score_payload_has_ht_matrix(self, mock_session, bundle):
        rows = await save_prediction_bundle(mock_session, 100, bundle)
        ht_row = next(r for r in rows if r.prediction_type == "ht_score")
        assert "ht_scoreline_matrix" in ht_row.payload
        assert len(ht_row.payload["ht_scoreline_matrix"]) == 5

    async def test_add_all_called_with_rows(self, mock_session, bundle):
        rows = await save_prediction_bundle(mock_session, 100, bundle)
        mock_session.add_all.assert_called_once_with(rows)

    async def test_flush_called(self, mock_session, bundle):
        await save_prediction_bundle(mock_session, 100, bundle)
        mock_session.flush.assert_awaited_once()

    async def test_append_only_no_execute_called(self, mock_session, bundle):
        """save_prediction_bundle must NOT call session.execute (no UPDATE)."""
        await save_prediction_bundle(mock_session, 100, bundle)
        mock_session.execute.assert_not_awaited()


# ── JSONB round-trip ─────────────────────────────────────────────────


class TestJSONBRoundTrip:
    """Verify each payload survives model_dump → model_validate."""

    def test_winner_roundtrip(self, bundle):
        raw = bundle.winner.model_dump(mode="json")
        restored = WinnerPayload.model_validate(raw)
        assert restored.p_home_win == bundle.winner.p_home_win
        assert restored.scoreline_matrix == bundle.winner.scoreline_matrix
        assert restored.confidence == bundle.winner.confidence

    def test_total_goals_roundtrip(self, bundle):
        raw = bundle.total_goals.model_dump(mode="json")
        restored = TotalGoalsPayload.model_validate(raw)
        assert restored.over_2_5 == bundle.total_goals.over_2_5
        assert restored.expected_total == bundle.total_goals.expected_total

    def test_ht_score_roundtrip(self, bundle):
        raw = bundle.ht_score.model_dump(mode="json")
        restored = HTScorePayload.model_validate(raw)
        assert restored.ht_lambda_home == bundle.ht_score.ht_lambda_home
        assert restored.ht_scoreline_matrix == bundle.ht_score.ht_scoreline_matrix

    def test_first_to_score_roundtrip(self, bundle):
        raw = bundle.first_to_score.model_dump(mode="json")
        restored = FirstToScorePayload.model_validate(raw)
        assert restored.p_home_first == bundle.first_to_score.p_home_first
        assert restored.p_no_goals == bundle.first_to_score.p_no_goals

    def test_full_bundle_roundtrip(self, bundle):
        """The entire bundle survives serialisation and reconstruction."""
        raw = bundle.model_dump(mode="json")
        restored = PredictionBundle.model_validate(raw)
        assert restored.stage == bundle.stage
        assert restored.model_version == bundle.model_version
        assert restored.winner.p_home_win == bundle.winner.p_home_win
        assert len(restored.winner.scoreline_matrix) == 8
        assert len(restored.ht_score.ht_scoreline_matrix) == 5


# ── save_outcome ─────────────────────────────────────────────────────


class TestSaveOutcome:
    async def test_execute_called(self, mock_session):
        await save_outcome(
            mock_session,
            fixture_id=100,
            home_team="Brazil",
            away_team="Germany",
            ft_home=2,
            ft_away=1,
            ht_home=1,
            ht_away=0,
            first_scorer_team="Brazil",
            kickoff_at=datetime(2026, 6, 11, 18, 0, tzinfo=timezone.utc),
        )
        mock_session.execute.assert_awaited_once()

    async def test_flush_called(self, mock_session):
        await save_outcome(
            mock_session,
            fixture_id=100,
            home_team="Brazil",
            away_team="Germany",
            ft_home=2,
            ft_away=1,
            kickoff_at=datetime(2026, 6, 11, 18, 0, tzinfo=timezone.utc),
        )
        mock_session.flush.assert_awaited_once()

    async def test_nullable_ht_fields(self, mock_session):
        """ht_home/ht_away can be None (AET/PEN or missing data)."""
        await save_outcome(
            mock_session,
            fixture_id=200,
            home_team="France",
            away_team="Argentina",
            ft_home=3,
            ft_away=3,
            ht_home=None,
            ht_away=None,
            first_scorer_team=None,
            kickoff_at=datetime(2026, 7, 13, 20, 0, tzinfo=timezone.utc),
        )
        mock_session.execute.assert_awaited_once()


# ── get_predictions_for_fixture ──────────────────────────────────────


class TestGetPredictions:
    async def test_returns_list(self, mock_session):
        row1 = _make_prediction_row(prediction_type="winner")
        row2 = _make_prediction_row(prediction_type="total_goals")

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [row1, row2]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        rows = await get_predictions_for_fixture(mock_session, 100)
        assert len(rows) == 2
        assert rows[0].prediction_type == "winner"

    async def test_empty_when_no_predictions(self, mock_session):
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        rows = await get_predictions_for_fixture(mock_session, 999)
        assert rows == []


# ── get_latest_predictions_for_fixture ───────────────────────────────


class TestGetLatestPredictions:
    async def test_returns_dict_keyed_by_type(self, mock_session):
        row_w = _make_prediction_row(prediction_type="winner")
        row_tg = _make_prediction_row(prediction_type="total_goals")

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [row_w, row_tg]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        latest = await get_latest_predictions_for_fixture(mock_session, 100)
        assert isinstance(latest, dict)
        assert "winner" in latest
        assert "total_goals" in latest
        assert latest["winner"].prediction_type == "winner"

    async def test_empty_dict_when_no_predictions(self, mock_session):
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        latest = await get_latest_predictions_for_fixture(mock_session, 999)
        assert latest == {}


# ── get_outcome ──────────────────────────────────────────────────────


class TestGetOutcome:
    async def test_returns_outcome_when_exists(self, mock_session):
        outcome = Outcome()
        outcome.fixture_id = 100
        outcome.home_team = "Brazil"
        outcome.away_team = "Germany"
        outcome.ft_home = 2
        outcome.ft_away = 1
        outcome.ht_home = 1
        outcome.ht_away = 0
        outcome.kickoff_at = datetime(2026, 6, 11, 18, 0, tzinfo=timezone.utc)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = outcome
        mock_session.execute.return_value = mock_result

        result = await get_outcome(mock_session, 100)
        assert result is not None
        assert result.fixture_id == 100
        assert result.ft_home == 2

    async def test_returns_none_when_missing(self, mock_session):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await get_outcome(mock_session, 999)
        assert result is None


# ── get_cached_bundle ────────────────────────────────────────────────


class TestGetCachedBundle:
    def _mock_scalars(self, mock_session, rows):
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = rows
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

    async def test_returns_dict_when_all_four_types_present(self, mock_session):
        rows = [
            _make_prediction_row(prediction_type=t)
            for t in PREDICTION_TYPES
        ]
        self._mock_scalars(mock_session, rows)

        cached = await get_cached_bundle(mock_session, 100, "pre_lineup")
        assert cached is not None
        assert set(cached.keys()) == set(PREDICTION_TYPES)

    async def test_returns_none_when_types_incomplete(self, mock_session):
        rows = [
            _make_prediction_row(prediction_type="winner"),
            _make_prediction_row(prediction_type="total_goals"),
        ]
        self._mock_scalars(mock_session, rows)

        cached = await get_cached_bundle(mock_session, 100, "pre_lineup")
        assert cached is None

    async def test_returns_none_when_empty(self, mock_session):
        self._mock_scalars(mock_session, [])
        cached = await get_cached_bundle(mock_session, 100, "pre_lineup")
        assert cached is None

    async def test_keeps_latest_per_type(self, mock_session):
        """When multiple rows per type exist, the first (newest) wins."""
        newer = _make_prediction_row(
            prediction_type="winner",
            made_at=datetime(2026, 6, 11, 18, 0, tzinfo=timezone.utc),
        )
        older = _make_prediction_row(
            prediction_type="winner",
            made_at=datetime(2026, 6, 11, 17, 0, tzinfo=timezone.utc),
        )
        other_types = [
            _make_prediction_row(prediction_type=t)
            for t in PREDICTION_TYPES
            if t != "winner"
        ]
        # Rows ordered newest-first (matching ORDER BY made_at DESC).
        self._mock_scalars(mock_session, [newer, older] + other_types)

        cached = await get_cached_bundle(mock_session, 100, "pre_lineup")
        assert cached is not None
        assert cached["winner"] is newer

    async def test_query_filters_by_prediction_type(self, mock_session):
        """Regression: the SQL query must include a prediction_type IN (...)
        filter so that reasoning and upset_index rows — which share the same
        fixture_id/stage — are excluded before the set-equality check.

        Without this filter, sibling reasoning rows pollute the result set
        and the set check ({4 types + reasoning + upset_index} != {4 types})
        returns None — a permanent false cache miss.
        """
        self._mock_scalars(mock_session, [])
        await get_cached_bundle(mock_session, 100, "pre_lineup")

        # Capture the SQLAlchemy Select statement passed to session.execute
        stmt = mock_session.execute.call_args[0][0]
        compiled_sql = str(stmt)

        # The compiled SQL must contain an IN clause on prediction_type
        assert "prediction_type IN" in compiled_sql, (
            "get_cached_bundle query is missing the prediction_type IN "
            "filter — reasoning/upset_index rows will pollute the cache check"
        )

    async def test_sibling_reasoning_rows_cause_false_miss(self, mock_session):
        """Documents the pollution scenario: if the SQL filter were removed
        and the DB returned reasoning + upset_index rows alongside the four
        prediction types, the set-equality check would fail (6 keys != 4)
        and return None — a false cache miss.

        This test locks in that the Python-level set check does NOT tolerate
        extra prediction_type values, reinforcing that the SQL filter is the
        sole defence against the pollution bug.
        """
        # Simulate what the DB would return WITHOUT the prediction_type filter:
        # all 4 prediction types + reasoning + upset_index = 6 rows
        rows = [
            _make_prediction_row(prediction_type=t)
            for t in PREDICTION_TYPES
        ]
        rows.append(_make_prediction_row(prediction_type="reasoning"))
        rows.append(_make_prediction_row(prediction_type="upset_index"))
        self._mock_scalars(mock_session, rows)

        cached = await get_cached_bundle(mock_session, 100, "pre_lineup")
        # The set check rejects extra types — this is the bug behaviour
        # that the SQL filter prevents from ever being reached.
        assert cached is None, (
            "Expected None when reasoning/upset_index rows leak into the "
            "result set (documents the pollution bug scenario)"
        )


# ── get_all_accuracy_rollups ─────────────────────────────────────────


class TestGetAllAccuracyRollups:
    async def test_returns_list(self, mock_session):
        rollup = AccuracyRollup()
        rollup.id = uuid.uuid4()
        rollup.window = "last_7d"
        rollup.prediction_type = "winner"
        rollup.total_predictions = 10

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [rollup]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await get_all_accuracy_rollups(mock_session)
        assert len(result) == 1
        assert result[0].window == "last_7d"

    async def test_empty_when_no_rollups(self, mock_session):
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await get_all_accuracy_rollups(mock_session)
        assert result == []


# ── save_live_prediction ─────────────────────────────────────────────


class TestSaveLivePrediction:
    async def test_creates_single_row(self, mock_session):
        mock_session.add = MagicMock()
        payload = {"method": "v1_lambda_remaining", "elapsed": 45}
        row = await save_live_prediction(mock_session, 100, payload)
        assert isinstance(row, Prediction)
        assert row.fixture_id == 100
        assert row.prediction_type == "live_winner"
        assert row.stage == "live"
        assert row.payload == payload

    async def test_flush_called(self, mock_session):
        mock_session.add = MagicMock()
        await save_live_prediction(
            mock_session, 100, {"elapsed": 30}
        )
        mock_session.flush.assert_awaited_once()

    async def test_model_version_set(self, mock_session):
        mock_session.add = MagicMock()
        row = await save_live_prediction(
            mock_session, 100, {"elapsed": 60}, model_version="test_v1"
        )
        assert row.model_version == "test_v1"

    async def test_add_called_not_add_all(self, mock_session):
        """Live predictions use session.add (single row), not add_all."""
        mock_session.add = MagicMock()
        await save_live_prediction(
            mock_session, 100, {"elapsed": 45}
        )
        mock_session.add.assert_called_once()


# ── get_cached_live_prediction ───────────────────────────────────────


class TestGetCachedLivePrediction:
    async def test_returns_row_when_fresh_and_elapsed_matches(
        self, mock_session
    ):
        row = _make_prediction_row(
            prediction_type="live_winner", stage="live"
        )
        row.payload = {"elapsed": 45, "p_home_win": 0.6}

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = row
        mock_session.execute.return_value = mock_result

        cached = await get_cached_live_prediction(
            mock_session, 100, elapsed=45
        )
        assert cached is row

    async def test_returns_none_when_elapsed_mismatch(self, mock_session):
        row = _make_prediction_row(
            prediction_type="live_winner", stage="live"
        )
        row.payload = {"elapsed": 45, "p_home_win": 0.6}

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = row
        mock_session.execute.return_value = mock_result

        # Request elapsed=46, cached has elapsed=45 → miss.
        cached = await get_cached_live_prediction(
            mock_session, 100, elapsed=46
        )
        assert cached is None

    async def test_returns_none_when_no_rows(self, mock_session):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        cached = await get_cached_live_prediction(
            mock_session, 100, elapsed=30
        )
        assert cached is None

    def test_live_cache_ttl_is_30_seconds(self):
        assert LIVE_CACHE_MAX_AGE_SECONDS == 30
