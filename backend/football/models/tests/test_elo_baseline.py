"""Unit tests for the naive Elo baseline model."""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backend.football.models.elo_baseline import (
    DEFAULT_RATING,
    EloModel,
    train,
)


def _make_matches(results: list[tuple[int, int, int, int]]) -> pd.DataFrame:
    """Build a DataFrame from (home_id, away_id, home_goals, away_goals) tuples."""
    rows = []
    base = pd.Timestamp("2023-01-01", tz="UTC")
    for i, (h_id, a_id, hg, ag) in enumerate(results):
        rows.append({
            "fixture_id": i,
            "league_id": 999,
            "season": 2023,
            "kickoff_utc": base + pd.Timedelta(days=i),
            "home_team_id": h_id,
            "home_team_name": f"Team_{h_id}",
            "away_team_id": a_id,
            "away_team_name": f"Team_{a_id}",
            "home_goals": hg,
            "away_goals": ag,
            "ht_home_goals": 0,
            "ht_away_goals": 0,
            "status_short": "FT",
        })
    df = pd.DataFrame(rows)
    df["kickoff_utc"] = pd.to_datetime(df["kickoff_utc"], utc=True)
    return df


class TestEloTrainPredict:
    def test_strong_team_rated_higher(self):
        """Team that wins repeatedly should have higher rating."""
        # Team 1 beats Team 2 ten times in a row.
        results = [(1, 2, 3, 0)] * 10
        model = train(_make_matches(results))

        assert model.ratings[1] > model.ratings[2]

    def test_strong_team_predicted_to_win(self):
        results = [(1, 2, 3, 0)] * 10
        model = train(_make_matches(results))

        pred = model.predict_match(home_team_id=1, away_team_id=2)
        assert pred["p_home_win"] > pred["p_away_win"]

    def test_probs_sum_to_one(self):
        results = [(1, 2, 2, 1), (2, 1, 0, 0), (1, 3, 1, 1)]
        model = train(_make_matches(results))

        pred = model.predict_match(1, 2)
        total = pred["p_home_win"] + pred["p_draw"] + pred["p_away_win"]
        assert total == pytest.approx(1.0)

    def test_unseen_team_gets_default_rating(self):
        results = [(1, 2, 1, 0)]
        model = train(_make_matches(results))

        pred = model.predict_match(home_team_id=999, away_team_id=1)
        assert pred["rating_home"] == DEFAULT_RATING

    def test_draw_prob_fixed(self):
        results = [(1, 2, 1, 0)]
        model = train(_make_matches(results))

        pred = model.predict_match(1, 2)
        assert pred["p_draw"] == 0.25

    def test_home_advantage_effect(self):
        """Equal-rated teams: home team should be slightly favoured."""
        results = [(1, 2, 1, 1)]  # One draw: ratings stay near equal.
        model = train(_make_matches(results))

        pred = model.predict_match(1, 2)
        assert pred["p_home_win"] > pred["p_away_win"]


class TestEloSaveLoad:
    def test_roundtrip(self):
        results = [(1, 2, 2, 0), (2, 3, 1, 1)]
        model = train(_make_matches(results))

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "elo.json"
            model.save(path)
            loaded = EloModel.load(path)

        assert loaded.training_matches == model.training_matches
        for tid in model.ratings:
            assert loaded.ratings[tid] == pytest.approx(model.ratings[tid])
