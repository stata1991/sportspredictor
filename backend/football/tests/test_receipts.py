"""Tests for Track Record match receipts (TRACK-2)."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from backend.football.evaluation.receipts import (
    build_match_receipt,
    is_friendly,
)

WINNER = lambda h, d, a: {"p_home_win": h, "p_draw": d, "p_away_win": a}  # noqa: E731
GOALS = lambda o, u: {"over_2_5": o, "under_2_5": u}  # noqa: E731


def _outcome(ft_home, ft_away, *, home="Mexico", away="South Africa",
             kickoff="2026-06-11T19:00:00+00:00", rnd="Group Stage - 1", fid=1):
    return SimpleNamespace(
        fixture_id=fid, home_team=home, away_team=away,
        ft_home=ft_home, ft_away=ft_away, round=rnd,
        kickoff_at=datetime.fromisoformat(kickoff),
    )


class TestWinner:
    def test_winner_hit(self):
        r = build_match_receipt(_outcome(2, 0), WINNER(0.6, 0.25, 0.15), None)
        assert r["winner_pick"] == "Mexico"
        assert r["winner_actual"] == "Mexico"
        assert r["winner_correct"] is True

    def test_winner_miss(self):
        # Picked home (Mexico), but away won.
        r = build_match_receipt(_outcome(0, 1), WINNER(0.6, 0.25, 0.15), None)
        assert r["winner_pick"] == "Mexico"
        assert r["winner_actual"] == "South Africa"
        assert r["winner_correct"] is False

    def test_draw_pick_and_draw_actual(self):
        r = build_match_receipt(_outcome(1, 1), WINNER(0.3, 0.5, 0.2), None)
        assert r["winner_pick"] == "Draw"
        assert r["winner_actual"] == "Draw"
        assert r["winner_correct"] is True

    def test_away_pick_hit(self):
        r = build_match_receipt(_outcome(0, 2), WINNER(0.2, 0.3, 0.5), None)
        assert r["winner_pick"] == "South Africa"
        assert r["winner_correct"] is True


class TestGoals:
    def test_over_hit(self):
        # Pick Over 2.5; 3 goals → over.
        r = build_match_receipt(_outcome(2, 1), None, GOALS(0.6, 0.4))
        assert r["goals_pick"] == "Over 2.5"
        assert r["goals_actual"] == 3
        assert r["goals_correct"] is True

    def test_under_hit(self):
        # Pick Under 2.5; 2 goals → under.
        r = build_match_receipt(_outcome(2, 0), None, GOALS(0.4, 0.6))
        assert r["goals_pick"] == "Under 2.5"
        assert r["goals_actual"] == 2
        assert r["goals_correct"] is True

    def test_over_miss(self):
        # Pick Over 2.5; 1 goal → under → miss.
        r = build_match_receipt(_outcome(1, 0), None, GOALS(0.55, 0.45))
        assert r["goals_pick"] == "Over 2.5"
        assert r["goals_correct"] is False


class TestMeta:
    def test_final_score_and_fields(self):
        r = build_match_receipt(_outcome(2, 0), WINNER(0.6, 0.25, 0.15), GOALS(0.4, 0.6))
        assert r["final_score"] == "2-0"
        assert r["home_team"] == "Mexico"
        assert r["away_team"] == "South Africa"
        assert r["round"] == "Group Stage - 1"

    def test_is_friendly_true_before_opener(self):
        assert is_friendly(datetime(2026, 6, 5, tzinfo=timezone.utc)) is True
        r = build_match_receipt(
            _outcome(1, 0, kickoff="2026-06-05T18:00:00+00:00"),
            WINNER(0.6, 0.25, 0.15), GOALS(0.4, 0.6),
        )
        assert r["is_friendly"] is True

    def test_is_friendly_false_on_or_after_opener(self):
        assert is_friendly(datetime(2026, 6, 11, tzinfo=timezone.utc)) is False
        r = build_match_receipt(_outcome(1, 0), WINNER(0.6, 0.25, 0.15), None)
        assert r["is_friendly"] is False

    def test_missing_payloads_yield_none_picks(self):
        r = build_match_receipt(_outcome(1, 1), None, None)
        assert r["winner_pick"] is None and r["winner_correct"] is None
        assert r["goals_pick"] is None and r["goals_correct"] is None
        assert r["goals_actual"] == 2  # still derivable from the score
