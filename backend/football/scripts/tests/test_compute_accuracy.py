"""Tests for the football accuracy rollup script.

Uses synthetic Prediction/Outcome ORM objects — does NOT hit a real
database.  Metric computation functions are pure Python and tested
directly with known inputs and expected outputs.
"""

from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from backend.football.scripts.compute_accuracy import (
    LOG_LOSS_EPS,
    RollupMetrics,
    _compute_first_to_score_metrics,
    _compute_ht_score_metrics,
    _compute_total_goals_metrics,
    _compute_winner_metrics,
    _run,
)
from backend.shared.models import Outcome, Prediction


# ── Helpers ──────────────────────────────────────────────────────────


def _pred(
    fixture_id: int = 100,
    prediction_type: str = "winner",
    payload: dict | None = None,
    made_at: datetime | None = None,
) -> Prediction:
    """Build a synthetic Prediction ORM object."""
    row = Prediction()
    row.id = uuid.uuid4()
    row.fixture_id = fixture_id
    row.prediction_type = prediction_type
    row.stage = "pre_lineup"
    row.made_at = made_at or datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc)
    row.payload = payload or {}
    row.model_version = "dixon_coles_v1"
    row.upset_index = None
    row.confidence = None
    return row


def _out(
    fixture_id: int = 100,
    ft_home: int = 2,
    ft_away: int = 1,
    ht_home: int | None = 1,
    ht_away: int | None = 0,
    first_scorer_team: str | None = None,
    home_team: str = "Brazil",
    away_team: str = "Germany",
    kickoff_at: datetime | None = None,
) -> Outcome:
    """Build a synthetic Outcome ORM object."""
    row = Outcome()
    row.fixture_id = fixture_id
    row.home_team = home_team
    row.away_team = away_team
    row.ft_home = ft_home
    row.ft_away = ft_away
    row.ht_home = ht_home
    row.ht_away = ht_away
    row.first_scorer_team = first_scorer_team
    row.kickoff_at = kickoff_at or datetime(
        2026, 6, 15, 18, 0, tzinfo=timezone.utc
    )
    return row


# ── Winner metrics ───────────────────────────────────────────────────


class TestWinnerMetrics:
    def test_perfect_home_win(self):
        p = _pred(payload={
            "p_home_win": 1.0, "p_draw": 0.0, "p_away_win": 0.0,
        })
        o = _out(ft_home=2, ft_away=1)
        m = _compute_winner_metrics([(p, o)])
        assert m.total_predictions == 1
        assert abs(m.brier_score) < 1e-10
        assert m.top_pick_hit_rate == 1.0

    def test_worst_case(self):
        p = _pred(payload={
            "p_home_win": 0.0, "p_draw": 0.0, "p_away_win": 1.0,
        })
        o = _out(ft_home=3, ft_away=0)
        m = _compute_winner_metrics([(p, o)])
        assert abs(m.brier_score - 2.0) < 1e-10
        assert m.top_pick_hit_rate == 0.0

    def test_draw(self):
        p = _pred(payload={
            "p_home_win": 0.2, "p_draw": 0.6, "p_away_win": 0.2,
        })
        o = _out(ft_home=1, ft_away=1)
        m = _compute_winner_metrics([(p, o)])
        expected = 0.2**2 + (0.6 - 1) ** 2 + 0.2**2
        assert abs(m.brier_score - expected) < 1e-10
        assert m.top_pick_hit_rate == 1.0

    def test_away_win(self):
        p = _pred(payload={
            "p_home_win": 0.3, "p_draw": 0.3, "p_away_win": 0.4,
        })
        o = _out(ft_home=0, ft_away=2)
        m = _compute_winner_metrics([(p, o)])
        expected = 0.3**2 + 0.3**2 + (0.4 - 1) ** 2
        assert abs(m.brier_score - expected) < 1e-10
        assert m.top_pick_hit_rate == 1.0

    def test_log_loss_perfect(self):
        p = _pred(payload={
            "p_home_win": 1.0, "p_draw": 0.0, "p_away_win": 0.0,
        })
        o = _out(ft_home=2, ft_away=1)
        m = _compute_winner_metrics([(p, o)])
        assert abs(m.log_loss) < 1e-10

    def test_multiple_averaged(self):
        p1 = _pred(fixture_id=1, payload={
            "p_home_win": 1.0, "p_draw": 0.0, "p_away_win": 0.0,
        })
        o1 = _out(fixture_id=1, ft_home=2, ft_away=0)

        p2 = _pred(fixture_id=2, payload={
            "p_home_win": 0.0, "p_draw": 0.0, "p_away_win": 1.0,
        })
        o2 = _out(fixture_id=2, ft_home=3, ft_away=0)

        m = _compute_winner_metrics([(p1, o1), (p2, o2)])
        assert m.total_predictions == 2
        assert abs(m.brier_score - 1.0) < 1e-10

    def test_empty(self):
        m = _compute_winner_metrics([])
        assert m.total_predictions == 0
        assert m.brier_score is None
        assert m.log_loss is None
        assert m.top_pick_hit_rate is None


# ── Total goals metrics ──────────────────────────────────────────────


class TestTotalGoalsMetrics:
    def test_over_correct(self):
        p = _pred(
            prediction_type="total_goals",
            payload={"over_2_5": 0.8, "under_2_5": 0.2},
        )
        o = _out(ft_home=2, ft_away=1)  # 3 goals
        m = _compute_total_goals_metrics([(p, o)])
        expected = (0.8 - 1) ** 2 + (0.2 - 0) ** 2
        assert abs(m.brier_score - expected) < 1e-10
        assert m.top_pick_hit_rate == 1.0

    def test_under_correct(self):
        p = _pred(
            prediction_type="total_goals",
            payload={"over_2_5": 0.3, "under_2_5": 0.7},
        )
        o = _out(ft_home=1, ft_away=1)  # 2 goals
        m = _compute_total_goals_metrics([(p, o)])
        expected = (0.3 - 0) ** 2 + (0.7 - 1) ** 2
        assert abs(m.brier_score - expected) < 1e-10
        assert m.top_pick_hit_rate == 1.0

    def test_exactly_two_is_under(self):
        p = _pred(
            prediction_type="total_goals",
            payload={"over_2_5": 0.5, "under_2_5": 0.5},
        )
        o = _out(ft_home=2, ft_away=0)  # 2 goals <= 2.5
        m = _compute_total_goals_metrics([(p, o)])
        expected = (0.5 - 0) ** 2 + (0.5 - 1) ** 2
        assert abs(m.brier_score - expected) < 1e-10

    def test_empty(self):
        m = _compute_total_goals_metrics([])
        assert m.total_predictions == 0
        assert m.brier_score is None


# ── HT score metrics ────────────────────────────────────────────────


class TestHTScoreMetrics:
    def _matrix_with_max(self, h: int, a: int) -> list[list[float]]:
        """Build a 5x5 matrix where (h, a) has the highest value."""
        m = [[0.01] * 5 for _ in range(5)]
        m[h][a] = 0.5
        return m

    def test_top_pick_correct(self):
        p = _pred(
            prediction_type="ht_score",
            payload={"ht_scoreline_matrix": self._matrix_with_max(1, 0)},
        )
        o = _out(ht_home=1, ht_away=0)
        m = _compute_ht_score_metrics([(p, o)])
        assert m.total_predictions == 1
        assert m.top_pick_hit_rate == 1.0
        assert m.brier_score is None
        assert m.log_loss is None

    def test_top_pick_wrong(self):
        p = _pred(
            prediction_type="ht_score",
            payload={"ht_scoreline_matrix": self._matrix_with_max(0, 0)},
        )
        o = _out(ht_home=1, ht_away=0)
        m = _compute_ht_score_metrics([(p, o)])
        assert m.top_pick_hit_rate == 0.0

    def test_null_ht_excluded(self):
        p = _pred(
            prediction_type="ht_score",
            payload={"ht_scoreline_matrix": self._matrix_with_max(0, 0)},
        )
        o = _out(ht_home=None, ht_away=None)
        m = _compute_ht_score_metrics([(p, o)])
        assert m.total_predictions == 0
        assert m.top_pick_hit_rate is None

    def test_empty(self):
        m = _compute_ht_score_metrics([])
        assert m.total_predictions == 0


# ── First-to-score metrics ──────────────────────────────────────────


class TestFirstToScoreMetrics:
    def test_home_first_correct(self):
        p = _pred(
            prediction_type="first_to_score",
            payload={
                "p_home_first": 0.6,
                "p_away_first": 0.3,
                "p_no_goals": 0.1,
            },
        )
        o = _out(
            first_scorer_team="Brazil",
            home_team="Brazil",
            away_team="Germany",
        )
        m = _compute_first_to_score_metrics([(p, o)])
        expected = (0.6 - 1) ** 2 + 0.3**2 + 0.1**2
        assert abs(m.brier_score - expected) < 1e-10
        assert m.top_pick_hit_rate == 1.0

    def test_away_first(self):
        p = _pred(
            prediction_type="first_to_score",
            payload={
                "p_home_first": 0.2,
                "p_away_first": 0.7,
                "p_no_goals": 0.1,
            },
        )
        o = _out(
            first_scorer_team="Germany",
            home_team="Brazil",
            away_team="Germany",
        )
        m = _compute_first_to_score_metrics([(p, o)])
        expected = 0.2**2 + (0.7 - 1) ** 2 + 0.1**2
        assert abs(m.brier_score - expected) < 1e-10

    def test_null_first_scorer_excluded(self):
        p = _pred(
            prediction_type="first_to_score",
            payload={
                "p_home_first": 0.5,
                "p_away_first": 0.3,
                "p_no_goals": 0.2,
            },
        )
        o = _out(first_scorer_team=None)
        m = _compute_first_to_score_metrics([(p, o)])
        assert m.total_predictions == 0
        assert m.brier_score is None
        assert m.log_loss is None
        assert m.top_pick_hit_rate is None

    def test_all_null_first_scorer(self):
        pairs = []
        for i in range(5):
            p = _pred(
                fixture_id=i,
                prediction_type="first_to_score",
                payload={
                    "p_home_first": 0.5,
                    "p_away_first": 0.3,
                    "p_no_goals": 0.2,
                },
            )
            o = _out(fixture_id=i, first_scorer_team=None)
            pairs.append((p, o))

        m = _compute_first_to_score_metrics(pairs)
        assert m.total_predictions == 0
        assert m.brier_score is None

    def test_mixed_null_and_valid(self):
        p1 = _pred(
            fixture_id=1,
            prediction_type="first_to_score",
            payload={
                "p_home_first": 1.0,
                "p_away_first": 0.0,
                "p_no_goals": 0.0,
            },
        )
        o1 = _out(
            fixture_id=1,
            first_scorer_team="Brazil",
            home_team="Brazil",
            away_team="Germany",
        )

        p2 = _pred(
            fixture_id=2,
            prediction_type="first_to_score",
            payload={
                "p_home_first": 0.5,
                "p_away_first": 0.3,
                "p_no_goals": 0.2,
            },
        )
        o2 = _out(fixture_id=2, first_scorer_team=None)

        m = _compute_first_to_score_metrics([(p1, o1), (p2, o2)])
        assert m.total_predictions == 1

    def test_empty(self):
        m = _compute_first_to_score_metrics([])
        assert m.total_predictions == 0


# ── Integration: _run() with no settled fixtures ─────────────────────


class TestRunIntegration:
    async def test_no_settled_exits_cleanly(self):
        """Empty DB returns 0 and prints message."""
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(
            return_value=AsyncMock(all=lambda: [])
        )

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "backend.football.scripts.compute_accuracy.get_db_session",
            return_value=mock_ctx,
        ):
            result = await _run()

        assert result == 0
