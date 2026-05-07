"""Tests for the football prediction engine (5.2.2).

Uses a small synthetic Dixon-Coles model to validate derivation maths,
schema construction, stage detection, and end-to-end engine behaviour.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from backend.football.models.dixon_coles import DixonColesModel
from backend.football.predictions.derivations import (
    HT_FT_RATIO,
    MAX_HT_GOALS,
    MAX_REMAINING_GOALS,
    derive_first_to_score,
    derive_ht_score,
    derive_live_v1,
    derive_total_goals,
    derive_winner,
)
from backend.football.predictions.engine import (
    CompletedFixtureError,
    NotPredictableError,
    PredictionEngine,
    detect_stage,
)
from backend.football.predictions.schemas import FixtureStage, PredictionBundle


# ── Fixtures ──────────────────────────────────────────────────────────


def _make_model() -> DixonColesModel:
    """Create a minimal 2-team Dixon-Coles model for testing."""
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
def model() -> DixonColesModel:
    return _make_model()


@pytest.fixture
def match_result(model: DixonColesModel) -> dict:
    return model.predict_match(1, 2)


# ── Stage detection ───────────────────────────────────────────────────


class TestDetectStage:
    # ── Not started (no lineups) → PRE_LINEUP ──
    def test_not_started_ns(self):
        assert detect_stage("NS") is FixtureStage.PRE_LINEUP

    def test_not_started_tbd(self):
        assert detect_stage("TBD") is FixtureStage.PRE_LINEUP

    # ── Not started (lineups available) → POST_LINEUP ──
    def test_post_lineup_ns_with_lineups(self):
        assert detect_stage("NS", has_lineups=True) is FixtureStage.POST_LINEUP

    def test_post_lineup_tbd_with_lineups(self):
        assert detect_stage("TBD", has_lineups=True) is FixtureStage.POST_LINEUP

    def test_pre_lineup_when_no_lineups(self):
        assert detect_stage("NS", has_lineups=False) is FixtureStage.PRE_LINEUP

    # ── Live ──
    def test_live_first_half(self):
        assert detect_stage("1H") is FixtureStage.LIVE

    def test_live_halftime(self):
        assert detect_stage("HT") is FixtureStage.LIVE

    def test_live_second_half(self):
        assert detect_stage("2H") is FixtureStage.LIVE

    def test_live_extra_time(self):
        assert detect_stage("ET") is FixtureStage.LIVE

    def test_live_penalties(self):
        assert detect_stage("P") is FixtureStage.LIVE

    # ── Completed (match finished cleanly) ──
    def test_completed_ft(self):
        assert detect_stage("FT") is FixtureStage.COMPLETED

    def test_completed_aet(self):
        assert detect_stage("AET") is FixtureStage.COMPLETED

    def test_completed_pen(self):
        assert detect_stage("PEN") is FixtureStage.COMPLETED

    # ── Not predictable (no match played / interrupted) ──
    def test_postponed(self):
        assert detect_stage("PST") is FixtureStage.NOT_PREDICTABLE

    def test_cancelled(self):
        assert detect_stage("CANC") is FixtureStage.NOT_PREDICTABLE

    def test_abandoned(self):
        assert detect_stage("ABD") is FixtureStage.NOT_PREDICTABLE

    def test_awarded(self):
        assert detect_stage("AWD") is FixtureStage.NOT_PREDICTABLE

    def test_walkover(self):
        assert detect_stage("WO") is FixtureStage.NOT_PREDICTABLE

    def test_suspended(self):
        assert detect_stage("SUSP") is FixtureStage.NOT_PREDICTABLE

    def test_interrupted(self):
        assert detect_stage("INT") is FixtureStage.NOT_PREDICTABLE

    def test_unknown_status(self):
        assert detect_stage("XYZ") is FixtureStage.NOT_PREDICTABLE

    # ── has_lineups ignored for non-NS statuses ──
    def test_lineups_ignored_for_live(self):
        assert detect_stage("1H", has_lineups=True) is FixtureStage.LIVE

    def test_lineups_ignored_for_completed(self):
        assert detect_stage("FT", has_lineups=True) is FixtureStage.COMPLETED


# ── derive_winner ─────────────────────────────────────────────────────


class TestDeriveWinner:
    def test_probabilities_sum_to_one(self, match_result):
        w = derive_winner(match_result)
        total = w["p_home_win"] + w["p_draw"] + w["p_away_win"]
        assert abs(total - 1.0) < 1e-4

    def test_scoreline_matrix_shape(self, match_result):
        w = derive_winner(match_result)
        assert len(w["scoreline_matrix"]) == 8
        assert all(len(row) == 8 for row in w["scoreline_matrix"])

    def test_scoreline_matrix_sums_to_one(self, match_result):
        w = derive_winner(match_result)
        total = sum(v for row in w["scoreline_matrix"] for v in row)
        assert abs(total - 1.0) < 1e-4

    def test_lambdas_positive(self, match_result):
        w = derive_winner(match_result)
        assert w["lambda_home"] > 0
        assert w["lambda_away"] > 0

    def test_confidence_normal_for_known_teams(self, match_result):
        w = derive_winner(match_result)
        assert w["confidence"] == "normal"

    def test_home_advantage_gives_higher_home_win(self, model):
        """With positive gamma and symmetric teams, home should have edge."""
        # Use the same team for both to isolate home advantage.
        symmetric = DixonColesModel(
            attack={1: 0.0, 2: 0.0},
            defence={1: 0.0, 2: 0.0},
            gamma=0.25,
            rho=-0.05,
            xi=0.0065,
            training_matches=100,
            training_window="test",
        )
        raw = symmetric.predict_match(1, 2)
        w = derive_winner(raw)
        assert w["p_home_win"] > w["p_away_win"]


# ── derive_total_goals ────────────────────────────────────────────────


class TestDeriveTotalGoals:
    def test_over_under_are_complements(self, match_result):
        matrix = match_result["scoreline_matrix"]
        tg = derive_total_goals(matrix)
        assert abs(tg["over_1_5"] + tg["under_1_5"] - 1.0) < 1e-4
        assert abs(tg["over_2_5"] + tg["under_2_5"] - 1.0) < 1e-4
        assert abs(tg["over_3_5"] + tg["under_3_5"] - 1.0) < 1e-4
        assert abs(tg["over_4_5"] + tg["under_4_5"] - 1.0) < 1e-4

    def test_expected_total_is_positive(self, match_result):
        matrix = match_result["scoreline_matrix"]
        tg = derive_total_goals(matrix)
        assert tg["expected_total"] > 0

    def test_over_lines_are_decreasing(self, match_result):
        """Higher lines should have lower over-probability."""
        matrix = match_result["scoreline_matrix"]
        tg = derive_total_goals(matrix)
        assert tg["over_1_5"] >= tg["over_2_5"]
        assert tg["over_2_5"] >= tg["over_3_5"]
        assert tg["over_3_5"] >= tg["over_4_5"]

    def test_expected_total_near_sum_of_lambdas(self, match_result):
        """Expected total ≈ lambda_home + lambda_away (with tau shift)."""
        matrix = match_result["scoreline_matrix"]
        tg = derive_total_goals(matrix)
        lam_sum = match_result["lambda_home"] + match_result["lambda_away"]
        # Allow some deviation due to tau correction and matrix truncation.
        assert abs(tg["expected_total"] - lam_sum) < 0.3


# ── derive_ht_score ───────────────────────────────────────────────────


class TestDeriveHTScore:
    def test_probabilities_sum_to_one(self, model):
        ht = derive_ht_score(model, 1, 2)
        total = ht["p_home_win"] + ht["p_draw"] + ht["p_away_win"]
        assert abs(total - 1.0) < 1e-4

    def test_matrix_shape_5x5(self, model):
        ht = derive_ht_score(model, 1, 2)
        assert len(ht["ht_scoreline_matrix"]) == 5
        assert all(len(row) == 5 for row in ht["ht_scoreline_matrix"])

    def test_matrix_sums_to_one(self, model):
        ht = derive_ht_score(model, 1, 2)
        total = sum(v for row in ht["ht_scoreline_matrix"] for v in row)
        assert abs(total - 1.0) < 1e-4

    def test_ht_lambdas_are_scaled(self, model, match_result):
        """HT lambdas ≈ FT lambdas × HT_FT_RATIO."""
        ht = derive_ht_score(model, 1, 2)
        assert abs(ht["ht_lambda_home"] - match_result["lambda_home"] * HT_FT_RATIO) < 1e-3
        assert abs(ht["ht_lambda_away"] - match_result["lambda_away"] * HT_FT_RATIO) < 1e-3

    def test_ht_draw_higher_than_ft(self, model, match_result):
        """Lower HT expected goals → more 0-0 draws → higher draw prob."""
        ht = derive_ht_score(model, 1, 2)
        ft = derive_winner(match_result)
        assert ht["p_draw"] > ft["p_draw"]


# ── derive_first_to_score ─────────────────────────────────────────────


class TestDeriveFirstToScore:
    def test_probabilities_sum_to_one(self, match_result):
        matrix = match_result["scoreline_matrix"]
        fts = derive_first_to_score(
            matrix, match_result["lambda_home"], match_result["lambda_away"],
        )
        total = fts["p_home_first"] + fts["p_away_first"] + fts["p_no_goals"]
        assert abs(total - 1.0) < 1e-4

    def test_p_no_goals_matches_matrix_00(self, match_result):
        """p_no_goals should equal the rounded scoreline_matrix[0][0]."""
        matrix = match_result["scoreline_matrix"]
        fts = derive_first_to_score(
            matrix, match_result["lambda_home"], match_result["lambda_away"],
        )
        assert abs(fts["p_no_goals"] - round(float(matrix[0, 0]), 6)) < 1e-6

    def test_stronger_team_more_likely_to_score_first(self, match_result):
        """Home team has higher lambda → more likely to score first."""
        matrix = match_result["scoreline_matrix"]
        fts = derive_first_to_score(
            matrix, match_result["lambda_home"], match_result["lambda_away"],
        )
        assert fts["p_home_first"] > fts["p_away_first"]

    def test_equal_lambdas_give_equal_first(self):
        """When lambdas are equal, both teams equally likely to score first."""
        model = DixonColesModel(
            attack={1: 0.0, 2: 0.0},
            defence={1: 0.0, 2: 0.0},
            gamma=0.0,  # No home advantage
            rho=0.0,
            xi=0.0065,
            training_matches=100,
            training_window="test",
        )
        raw = model.predict_match(1, 2)
        fts = derive_first_to_score(
            raw["scoreline_matrix"], raw["lambda_home"], raw["lambda_away"],
        )
        assert abs(fts["p_home_first"] - fts["p_away_first"]) < 1e-4


# ── PredictionEngine ──────────────────────────────────────────────────


class TestPredictionEngine:
    @pytest.fixture
    def engine(self, tmp_path, model):
        """Save the synthetic model to a temp file and load it via engine."""
        model_path = tmp_path / "test_model.json"
        model.save(model_path)
        return PredictionEngine(model_path=model_path)

    def test_predict_returns_bundle(self, engine):
        bundle = engine.predict(1, 2, "NS")
        assert isinstance(bundle, PredictionBundle)

    def test_predict_stage_pre_lineup(self, engine):
        bundle = engine.predict(1, 2, "NS")
        assert bundle.stage is FixtureStage.PRE_LINEUP

    def test_predict_stage_post_lineup(self, engine):
        bundle = engine.predict(1, 2, "NS", has_lineups=True)
        assert bundle.stage is FixtureStage.POST_LINEUP

    def test_predict_stage_live(self, engine):
        bundle = engine.predict(1, 2, "1H")
        assert bundle.stage is FixtureStage.LIVE

    def test_completed_raises_completed_fixture_error(self, engine):
        """FT must raise CompletedFixtureError, NOT NotPredictableError."""
        with pytest.raises(CompletedFixtureError) as exc_info:
            engine.predict(1, 2, "FT")
        assert exc_info.value.status == "FT"

    def test_completed_aet_raises_completed_fixture_error(self, engine):
        with pytest.raises(CompletedFixtureError):
            engine.predict(1, 2, "AET")

    def test_completed_pen_raises_completed_fixture_error(self, engine):
        with pytest.raises(CompletedFixtureError):
            engine.predict(1, 2, "PEN")

    def test_cancelled_raises_not_predictable(self, engine):
        with pytest.raises(NotPredictableError):
            engine.predict(1, 2, "CANC")

    def test_postponed_raises_not_predictable(self, engine):
        with pytest.raises(NotPredictableError):
            engine.predict(1, 2, "PST")

    def test_completed_is_not_not_predictable(self, engine):
        """Ensure completed and not_predictable are distinct error types."""
        with pytest.raises(CompletedFixtureError):
            engine.predict(1, 2, "FT")
        # Confirm it does NOT raise NotPredictableError
        with pytest.raises(Exception) as exc_info:
            engine.predict(1, 2, "FT")
        assert not isinstance(exc_info.value, NotPredictableError)

    def test_model_version(self, engine):
        bundle = engine.predict(1, 2, "NS")
        assert bundle.model_version == "dixon_coles_v1"

    def test_all_four_types_present(self, engine):
        bundle = engine.predict(1, 2, "NS")
        assert bundle.winner is not None
        assert bundle.total_goals is not None
        assert bundle.ht_score is not None
        assert bundle.first_to_score is not None

    def test_winner_matrix_in_bundle(self, engine):
        bundle = engine.predict(1, 2, "NS")
        assert len(bundle.winner.scoreline_matrix) == 8

    def test_ht_matrix_in_bundle(self, engine):
        bundle = engine.predict(1, 2, "NS")
        assert len(bundle.ht_score.ht_scoreline_matrix) == 5

    def test_unseen_team_confidence(self, engine):
        """Team 999 is not in the model → confidence should be low_data."""
        bundle = engine.predict(1, 999, "NS")
        assert bundle.confidence == "low_data"

    def test_bundle_serialises_to_dict(self, engine):
        """Ensure the bundle is JSON-serialisable (for JSONB persistence)."""
        bundle = engine.predict(1, 2, "NS")
        d = bundle.model_dump(mode="json")
        assert "winner" in d
        assert "total_goals" in d
        assert "ht_score" in d
        assert "first_to_score" in d
        assert isinstance(d["winner"]["scoreline_matrix"], list)


# ── derive_live_v1 ───────────────────────────────────────────────────


class TestDeriveLiveV1:
    def test_probabilities_sum_to_one(self, match_result):
        live = derive_live_v1(
            match_result["lambda_home"],
            match_result["lambda_away"],
            elapsed=45,
            home_goals=1,
            away_goals=0,
        )
        total = live["p_home_win"] + live["p_draw"] + live["p_away_win"]
        assert abs(total - 1.0) < 1e-4

    def test_remaining_lambdas_scale_with_time(self, match_result):
        """At 45 min, remaining lambdas should be ~half of pre-match."""
        live = derive_live_v1(
            match_result["lambda_home"],
            match_result["lambda_away"],
            elapsed=45,
            home_goals=0,
            away_goals=0,
        )
        assert abs(
            live["remaining_lambda_home"]
            - match_result["lambda_home"] * 0.5
        ) < 1e-3

    def test_full_time_gives_zero_remaining(self, match_result):
        live = derive_live_v1(
            match_result["lambda_home"],
            match_result["lambda_away"],
            elapsed=90,
            home_goals=2,
            away_goals=1,
        )
        assert live["remaining_lambda_home"] == 0.0
        assert live["remaining_lambda_away"] == 0.0
        # With zero remaining time and home leading, p_home_win ≈ 1.0.
        assert live["p_home_win"] > 0.999

    def test_leading_team_has_higher_win_prob(self, match_result):
        """Team leading 2-0 at 60' should have high win probability."""
        live = derive_live_v1(
            match_result["lambda_home"],
            match_result["lambda_away"],
            elapsed=60,
            home_goals=2,
            away_goals=0,
        )
        assert live["p_home_win"] > 0.8

    def test_method_field_present(self, match_result):
        live = derive_live_v1(
            match_result["lambda_home"],
            match_result["lambda_away"],
            elapsed=30,
            home_goals=0,
            away_goals=0,
        )
        assert live["method"] == "v1_lambda_remaining"

    def test_elapsed_clamped_to_90(self, match_result):
        """Extra time minutes (>90) should clamp to 90."""
        live = derive_live_v1(
            match_result["lambda_home"],
            match_result["lambda_away"],
            elapsed=120,
            home_goals=1,
            away_goals=1,
        )
        assert live["elapsed"] == 90
        assert live["remaining_lambda_home"] == 0.0

    def test_kickoff_has_full_remaining(self, match_result):
        live = derive_live_v1(
            match_result["lambda_home"],
            match_result["lambda_away"],
            elapsed=0,
            home_goals=0,
            away_goals=0,
        )
        assert abs(
            live["remaining_lambda_home"] - match_result["lambda_home"]
        ) < 1e-4
