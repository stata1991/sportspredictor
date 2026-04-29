"""Unit tests for the Dixon-Coles model.

Uses synthetic match data — no real API calls or historical data.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backend.football.models.dixon_coles import (
    DEFAULT_PRIOR_STRENGTH,
    DixonColesModel,
    MAX_GOALS,
    _shrink_rating,
    _tau,
    train,
)


def _synthetic_matches(
    *,
    n_matches: int = 200,
    strong_team: int = 1,
    weak_team: int = 2,
    neutral_a: int = 3,
    neutral_b: int = 4,
    seed: int = 42,
) -> pd.DataFrame:
    """Generate synthetic match data where team 1 is clearly stronger.

    Strong team scores ~2.5 goals on average, concedes ~0.8.
    Weak team scores ~0.6 goals on average, concedes ~2.2.
    Neutral teams score ~1.2 goals on average.
    """
    rng = np.random.RandomState(seed)
    rows = []
    base_date = pd.Timestamp("2023-01-01", tz="UTC")

    teams = [strong_team, weak_team, neutral_a, neutral_b]
    # Expected goals matrix: attack_strength[i] against defence_weakness[j]
    attack = {strong_team: 2.5, weak_team: 0.6, neutral_a: 1.2, neutral_b: 1.2}
    defence = {strong_team: 0.8, weak_team: 2.2, neutral_a: 1.3, neutral_b: 1.3}

    match_idx = 0
    for _ in range(n_matches):
        h, a = rng.choice(teams, size=2, replace=False)
        lam_h = attack[h] * (defence[a] / 1.3)  # scale by opponent weakness
        lam_a = attack[a] * (defence[h] / 1.3)
        hg = rng.poisson(lam_h)
        ag = rng.poisson(lam_a)
        rows.append({
            "fixture_id": match_idx,
            "league_id": 999,
            "season": 2023,
            "kickoff_utc": base_date + pd.Timedelta(days=match_idx),
            "home_team_id": h,
            "home_team_name": f"Team_{h}",
            "away_team_id": a,
            "away_team_name": f"Team_{a}",
            "home_goals": hg,
            "away_goals": ag,
            "ht_home_goals": 0,
            "ht_away_goals": 0,
            "status_short": "FT",
        })
        match_idx += 1

    df = pd.DataFrame(rows)
    df["kickoff_utc"] = pd.to_datetime(df["kickoff_utc"], utc=True)
    return df


class TestTau:
    """Tests for the Dixon-Coles tau correction function."""

    def test_tau_non_low_score_returns_one(self):
        assert _tau(2, 1, 1.5, 1.0, -0.1) == 1.0
        assert _tau(3, 3, 1.5, 1.0, -0.1) == 1.0

    def test_tau_zero_zero(self):
        rho = -0.1
        val = _tau(0, 0, 1.5, 1.2, rho)
        assert val == pytest.approx(1.0 - 1.5 * 1.2 * rho)

    def test_tau_one_zero(self):
        rho = -0.1
        val = _tau(1, 0, 1.5, 1.2, rho)
        assert val == pytest.approx(1.0 + 1.2 * rho)

    def test_tau_zero_one(self):
        rho = -0.1
        val = _tau(0, 1, 1.5, 1.2, rho)
        assert val == pytest.approx(1.0 + 1.5 * rho)

    def test_tau_one_one(self):
        rho = -0.1
        val = _tau(1, 1, 1.5, 1.2, rho)
        assert val == pytest.approx(1.0 - rho)


class TestTrainAndPredict:
    """Integration tests: train on synthetic data, then predict."""

    @pytest.fixture
    def model(self) -> DixonColesModel:
        df = _synthetic_matches(n_matches=300, seed=42)
        return train(df, xi=0.0)  # no decay for synthetic data

    def test_strong_team_favoured(self, model: DixonColesModel):
        """Strong team (id=1) should be predicted to beat weak team (id=2)."""
        pred = model.predict_match(home_team_id=1, away_team_id=2)
        assert pred["p_home_win"] > 0.5, (
            f"Expected P(strong wins) > 0.5, got {pred['p_home_win']:.3f}"
        )

    def test_strong_team_favoured_even_away(self, model: DixonColesModel):
        """Strong team should still be favoured when playing away."""
        pred = model.predict_match(home_team_id=2, away_team_id=1)
        assert pred["p_away_win"] > pred["p_home_win"], (
            f"Expected P(strong wins away) > P(weak wins home), "
            f"got away={pred['p_away_win']:.3f} home={pred['p_home_win']:.3f}"
        )

    def test_scoreline_matrix_sums_to_one(self, model: DixonColesModel):
        """Scoreline probability matrix should sum to approximately 1."""
        pred = model.predict_match(home_team_id=1, away_team_id=2)
        total = pred["scoreline_matrix"].sum()
        assert 0.99 <= total <= 1.01, f"Matrix sum = {total:.6f}"

    def test_outcome_probs_sum_to_one(self, model: DixonColesModel):
        """P(home) + P(draw) + P(away) should sum to ~1."""
        pred = model.predict_match(home_team_id=1, away_team_id=2)
        total = pred["p_home_win"] + pred["p_draw"] + pred["p_away_win"]
        assert 0.99 <= total <= 1.01, f"Sum = {total:.6f}"

    def test_symmetric_matchup(self, model: DixonColesModel):
        """Neutral A vs Neutral A: P(home) ≈ P(away) within reason.

        Not exactly equal because of home advantage (gamma), but the
        home/away ratio should reflect gamma, not a team-quality gap.
        """
        # Neutral_a (id=3) vs itself.
        pred = model.predict_match(home_team_id=3, away_team_id=3)
        # Home advantage means P(home) > P(away), but difference should be modest.
        diff = abs(pred["p_home_win"] - pred["p_away_win"])
        assert diff < 0.25, (
            f"Symmetric matchup too asymmetric: "
            f"home={pred['p_home_win']:.3f}, away={pred['p_away_win']:.3f}"
        )

    def test_scoreline_matrix_shape(self, model: DixonColesModel):
        pred = model.predict_match(home_team_id=1, away_team_id=2)
        assert pred["scoreline_matrix"].shape == (MAX_GOALS, MAX_GOALS)

    def test_lambda_positive(self, model: DixonColesModel):
        pred = model.predict_match(home_team_id=1, away_team_id=2)
        assert pred["lambda_home"] > 0
        assert pred["lambda_away"] > 0


class TestSaveLoad:
    """Tests for model serialisation round-trip."""

    def test_save_load_roundtrip(self):
        df = _synthetic_matches(n_matches=150, seed=99)
        model = train(df, xi=0.0)

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "model.json"
            model.save(path)

            loaded = DixonColesModel.load(path)

        # Verify parameters match.
        assert loaded.gamma == pytest.approx(model.gamma)
        assert loaded.rho == pytest.approx(model.rho)
        assert loaded.xi == model.xi
        assert loaded.training_matches == model.training_matches
        assert loaded.training_window == model.training_window
        assert set(loaded.attack.keys()) == set(model.attack.keys())
        for tid in model.attack:
            assert loaded.attack[tid] == pytest.approx(model.attack[tid])
            assert loaded.defence[tid] == pytest.approx(model.defence[tid])

    def test_saved_json_is_valid(self):
        df = _synthetic_matches(n_matches=100, seed=7)
        model = train(df, xi=0.0)

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "model.json"
            model.save(path)

            with open(path) as f:
                data = json.load(f)

        assert data["model"] == "dixon_coles"
        assert data["version"] == 1
        assert "saved_at" in data
        assert isinstance(data["attack"], dict)
        assert isinstance(data["defence"], dict)

    def test_predictions_match_after_load(self):
        df = _synthetic_matches(n_matches=150, seed=55)
        model = train(df, xi=0.0)

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "model.json"
            model.save(path)
            loaded = DixonColesModel.load(path)

        pred_orig = model.predict_match(1, 2)
        pred_loaded = loaded.predict_match(1, 2)

        assert pred_orig["p_home_win"] == pytest.approx(pred_loaded["p_home_win"])
        assert pred_orig["p_draw"] == pytest.approx(pred_loaded["p_draw"])
        assert pred_orig["p_away_win"] == pytest.approx(pred_loaded["p_away_win"])


class TestUnseenTeam:
    """Tests for unseen-team fallback behaviour."""

    def test_unseen_team_returns_low_data_confidence(self):
        df = _synthetic_matches(n_matches=100, seed=42)
        model = train(df, xi=0.0)

        # Team 999 was never in training data.
        pred = model.predict_match(home_team_id=999, away_team_id=1)
        assert pred["confidence"] == "low_data"

    def test_unseen_team_still_produces_valid_probs(self):
        df = _synthetic_matches(n_matches=100, seed=42)
        model = train(df, xi=0.0)

        pred = model.predict_match(home_team_id=999, away_team_id=998)
        total = pred["p_home_win"] + pred["p_draw"] + pred["p_away_win"]
        assert 0.99 <= total <= 1.01

    def test_known_team_returns_normal_confidence(self):
        df = _synthetic_matches(n_matches=100, seed=42)
        model = train(df, xi=0.0)

        pred = model.predict_match(home_team_id=1, away_team_id=2)
        assert pred["confidence"] == "normal"


class TestShrinkRating:
    """Tests for the _shrink_rating helper."""

    def test_zero_matches_returns_prior(self):
        assert _shrink_rating(2.0, 0, 0.0, 10) == 0.0

    def test_high_matches_preserves_raw(self):
        # 100 matches, prior_strength=10 → weight = 100/110 ≈ 0.909
        result = _shrink_rating(2.0, 100, 0.0, 10)
        assert result == pytest.approx(2.0 * 100 / 110)

    def test_equal_to_prior_strength_gives_half(self):
        # n = prior_strength → weight = 0.5
        result = _shrink_rating(2.0, 10, 0.0, 10)
        assert result == pytest.approx(1.0)

    def test_formula_exact(self):
        raw, n, prior_mean, ps = 1.5, 6, -0.25, 10
        expected = (6 / 16) * 1.5 + (10 / 16) * (-0.25)
        assert _shrink_rating(raw, n, prior_mean, ps) == pytest.approx(expected)


class TestShrinkageIntegration:
    """Tests for Bayesian shrinkage in the full model."""

    def test_shrinkage_pulls_low_data_toward_mean(self):
        """A team with few matches should have ratings closer to the
        population mean than the raw MLE values."""
        attack = {1: 2.0, 2: -1.5, 3: 0.0}
        defence = {1: -1.0, 2: 0.5, 3: 0.0}
        match_counts = {1: 50, 2: 3, 3: 30}

        model = DixonColesModel(
            attack=attack, defence=defence,
            gamma=0.25, rho=-0.05, xi=0.0065,
            training_matches=100, training_window="test",
            match_counts=match_counts, prior_strength=10,
        )

        # Team 2 (3 matches) should be pulled heavily toward mean.
        attack_mean = np.mean(list(attack.values()))
        raw_2 = attack[2]
        shrunk_2 = model.attack[2]
        # Shrunk value should be between raw and mean.
        assert abs(shrunk_2 - attack_mean) < abs(raw_2 - attack_mean)

    def test_shrinkage_barely_affects_high_data(self):
        """A team with many matches should retain most of its raw rating."""
        attack = {1: 2.0, 2: -1.5, 3: 0.0}
        defence = {1: -1.0, 2: 0.5, 3: 0.0}
        match_counts = {1: 50, 2: 3, 3: 30}

        model = DixonColesModel(
            attack=attack, defence=defence,
            gamma=0.25, rho=-0.05, xi=0.0065,
            training_matches=100, training_window="test",
            match_counts=match_counts, prior_strength=10,
        )

        # Team 1 (50 matches): weight = 50/60 ≈ 0.833 → retains ~83%.
        assert abs(model.attack[1] - attack[1]) < 0.4

    def test_no_match_counts_disables_shrinkage(self):
        """Without match_counts, ratings should be unchanged."""
        attack = {1: 2.0, 2: -1.5}
        defence = {1: -1.0, 2: 0.5}

        model = DixonColesModel(
            attack=attack, defence=defence,
            gamma=0.25, rho=-0.05, xi=0.0065,
            training_matches=100, training_window="test",
            match_counts=None,
        )

        assert model.attack[1] == 2.0
        assert model.attack[2] == -1.5

    def test_prior_strength_zero_disables_shrinkage(self):
        attack = {1: 2.0, 2: -1.5}
        defence = {1: -1.0, 2: 0.5}
        match_counts = {1: 5, 2: 3}

        model = DixonColesModel(
            attack=attack, defence=defence,
            gamma=0.25, rho=-0.05, xi=0.0065,
            training_matches=100, training_window="test",
            match_counts=match_counts, prior_strength=0,
        )

        assert model.attack[1] == 2.0
        assert model.attack[2] == -1.5

    def test_low_data_flagged_for_sparse_team(self):
        """Teams with match_count < prior_strength should be low_data."""
        attack = {1: 1.0, 2: -0.5}
        defence = {1: -0.5, 2: 0.3}
        match_counts = {1: 50, 2: 5}

        model = DixonColesModel(
            attack=attack, defence=defence,
            gamma=0.25, rho=-0.05, xi=0.0065,
            training_matches=100, training_window="test",
            match_counts=match_counts, prior_strength=10,
        )

        pred = model.predict_match(1, 2)
        assert pred["confidence"] == "low_data"

    def test_normal_confidence_for_sufficient_data(self):
        attack = {1: 1.0, 2: -0.5}
        defence = {1: -0.5, 2: 0.3}
        match_counts = {1: 50, 2: 15}

        model = DixonColesModel(
            attack=attack, defence=defence,
            gamma=0.25, rho=-0.05, xi=0.0065,
            training_matches=100, training_window="test",
            match_counts=match_counts, prior_strength=10,
        )

        pred = model.predict_match(1, 2)
        assert pred["confidence"] == "normal"

    def test_save_load_preserves_shrinkage(self):
        """Save/load roundtrip should produce identical shrunk ratings."""
        attack = {1: 2.0, 2: -1.5, 3: 0.0}
        defence = {1: -1.0, 2: 0.5, 3: 0.0}
        match_counts = {1: 50, 2: 3, 3: 30}

        model = DixonColesModel(
            attack=attack, defence=defence,
            gamma=0.25, rho=-0.05, xi=0.0065,
            training_matches=100, training_window="test",
            match_counts=match_counts, prior_strength=10,
        )

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "model.json"
            model.save(path)

            # Verify JSON has raw ratings.
            with open(path) as f:
                data = json.load(f)
            assert float(data["attack"]["2"]) == pytest.approx(-1.5)

            loaded = DixonColesModel.load(path, prior_strength=10)

        for tid in attack:
            assert loaded.attack[tid] == pytest.approx(model.attack[tid])
            assert loaded.defence[tid] == pytest.approx(model.defence[tid])
        assert loaded.match_counts == model.match_counts

    def test_load_different_prior_strength(self):
        """Loading with different prior_strength should change ratings."""
        attack = {1: 2.0, 2: -1.5}
        defence = {1: -1.0, 2: 0.5}
        match_counts = {1: 50, 2: 3}

        model = DixonColesModel(
            attack=attack, defence=defence,
            gamma=0.25, rho=-0.05, xi=0.0065,
            training_matches=100, training_window="test",
            match_counts=match_counts, prior_strength=10,
        )

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "model.json"
            model.save(path)

            loaded_5 = DixonColesModel.load(path, prior_strength=5)
            loaded_20 = DixonColesModel.load(path, prior_strength=20)

        # Team 2 (3 matches): more shrinkage with higher prior_strength.
        # prior_strength=5:  weight = 3/8  = 0.375
        # prior_strength=20: weight = 3/23 = 0.130
        assert abs(loaded_5.attack[2]) > abs(loaded_20.attack[2])

    def test_train_produces_match_counts(self):
        """train() should automatically compute match_counts."""
        df = _synthetic_matches(n_matches=100, seed=42)
        model = train(df, xi=0.0)

        assert model.match_counts is not None
        # 4 teams in synthetic data, all should have counts.
        assert len(model.match_counts) == 4
        assert all(c > 0 for c in model.match_counts.values())
