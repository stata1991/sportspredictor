"""Naive Elo baseline for football match prediction.

A deliberately simple baseline — the point is to establish a credible
floor, not to compete with Dixon-Coles.

Implementation
--------------
- Each team has a rating R_i, default 1500.
- After each match, update using standard Elo with K=20.
- For prediction:
      p_binary_home = 1 / (1 + 10^((R_away - R_home - HOME_ADV) / 400))
      p_draw = 0.25  (fixed)
      p_home = 0.75 * p_binary_home
      p_away = 0.75 - p_home

  This is intentionally crude — a baseline, not a competitor.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

DEFAULT_RATING = 1500.0
K_FACTOR = 20.0
HOME_ADVANTAGE = 100.0
DRAW_PROB = 0.25


class EloModel:
    """Fitted Elo rating model."""

    def __init__(
        self,
        ratings: dict[int, float],
        training_matches: int,
        training_window: str,
        team_names: dict[int, str] | None = None,
    ) -> None:
        self.ratings = ratings
        self.training_matches = training_matches
        self.training_window = training_window
        self.team_names = team_names or {}

    def _get_rating(self, team_id: int) -> float:
        return self.ratings.get(team_id, DEFAULT_RATING)

    def predict_match(
        self, home_team_id: int, away_team_id: int,
    ) -> dict[str, Any]:
        """Predict outcome probabilities for a match.

        Returns dict with p_home_win, p_draw, p_away_win.
        """
        r_home = self._get_rating(home_team_id)
        r_away = self._get_rating(away_team_id)

        # Binary win probability (ignoring draws).
        exponent = (r_away - r_home - HOME_ADVANTAGE) / 400.0
        p_binary_home = 1.0 / (1.0 + 10.0 ** exponent)

        # Allocate the non-draw probability mass.
        p_home_win = (1.0 - DRAW_PROB) * p_binary_home
        p_away_win = (1.0 - DRAW_PROB) * (1.0 - p_binary_home)
        p_draw = DRAW_PROB

        return {
            "p_home_win": p_home_win,
            "p_draw": p_draw,
            "p_away_win": p_away_win,
            "rating_home": r_home,
            "rating_away": r_away,
        }

    # ── Serialisation ──────────────────────────────────────────────

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "model": "elo_baseline",
            "version": 1,
            "ratings": {str(k): v for k, v in self.ratings.items()},
            "training_matches": self.training_matches,
            "training_window": self.training_window,
            "team_names": {str(k): v for k, v in self.team_names.items()},
            "k_factor": K_FACTOR,
            "home_advantage": HOME_ADVANTAGE,
            "draw_prob": DRAW_PROB,
            "saved_at": datetime.now(timezone.utc).isoformat(),
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        logger.info("Elo model saved to %s (%d teams)", path, len(self.ratings))

    @classmethod
    def load(cls, path: str | Path) -> EloModel:
        with open(path) as f:
            data = json.load(f)
        return cls(
            ratings={int(k): v for k, v in data["ratings"].items()},
            training_matches=data["training_matches"],
            training_window=data["training_window"],
            team_names={int(k): v for k, v in data.get("team_names", {}).items()},
        )


# ── Training ───────────────────────────────────────────────────────

def train(df: pd.DataFrame) -> EloModel:
    """Train Elo ratings by replaying matches chronologically.

    Parameters
    ----------
    df:
        DataFrame with columns: home_team_id, away_team_id, home_goals,
        away_goals, kickoff_utc.  Must be sorted by kickoff_utc.
    """
    if df.empty:
        raise ValueError("Cannot train on empty DataFrame")

    df = df.sort_values("kickoff_utc").reset_index(drop=True)
    ratings: dict[int, float] = {}

    for _, row in df.iterrows():
        h_id = int(row["home_team_id"])
        a_id = int(row["away_team_id"])
        r_h = ratings.get(h_id, DEFAULT_RATING)
        r_a = ratings.get(a_id, DEFAULT_RATING)

        # Expected score (binary, 0-1 scale).
        e_h = 1.0 / (1.0 + 10.0 ** ((r_a - r_h - HOME_ADVANTAGE) / 400.0))
        e_a = 1.0 - e_h

        # Actual score: 1 for win, 0.5 for draw, 0 for loss.
        hg = int(row["home_goals"])
        ag = int(row["away_goals"])
        if hg > ag:
            s_h, s_a = 1.0, 0.0
        elif hg < ag:
            s_h, s_a = 0.0, 1.0
        else:
            s_h, s_a = 0.5, 0.5

        ratings[h_id] = r_h + K_FACTOR * (s_h - e_h)
        ratings[a_id] = r_a + K_FACTOR * (s_a - e_a)

    # Team name lookup.
    team_names: dict[int, str] = {}
    for col_id, col_name in [("home_team_id", "home_team_name"), ("away_team_id", "away_team_name")]:
        for tid, name in zip(df[col_id], df[col_name]):
            if tid not in team_names:
                team_names[tid] = name

    min_date = df["kickoff_utc"].min()
    max_date = df["kickoff_utc"].max()
    window = f"{min_date.date()} to {max_date.date()}"

    model = EloModel(
        ratings=ratings,
        training_matches=len(df),
        training_window=window,
        team_names=team_names,
    )

    logger.info(
        "Elo training complete: %d matches, %d teams, "
        "rating range %.0f–%.0f",
        len(df), len(ratings),
        min(ratings.values()), max(ratings.values()),
    )

    return model
