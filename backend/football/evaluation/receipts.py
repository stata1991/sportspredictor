"""Match-wise Track Record receipts (TRACK-2).

Pure derivation: turn an outcome + its latest winner/total_goals prediction
payloads into a "what we called vs what happened" receipt. No DB, no I/O.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

# The 2026 World Cup opener. Anything kicking off before this is a
# pre-tournament warm-up — the ONLY non-WC fixtures the system ever
# predicts, so a single date threshold cleanly separates the two.
TOURNAMENT_START = datetime(2026, 6, 11, tzinfo=timezone.utc)

# Total-goals line the predictions are expressed on.
GOALS_LINE = 2.5


def is_friendly(kickoff_at: datetime) -> bool:
    """True for a pre-tournament warm-up (kickoff before the WC opener)."""
    return kickoff_at < TOURNAMENT_START


def _winner_pick(payload: dict[str, Any], home: str, away: str) -> str:
    """The side the winner prediction favoured: home team, "Draw", or away."""
    options = [
        (payload["p_home_win"], home),
        (payload["p_draw"], "Draw"),
        (payload["p_away_win"], away),
    ]
    return max(options, key=lambda o: o[0])[1]


def _winner_actual(ft_home: int, ft_away: int, home: str, away: str) -> str:
    if ft_home > ft_away:
        return home
    if ft_home == ft_away:
        return "Draw"
    return away


def _goals_pick(payload: dict[str, Any]) -> str:
    return "Over 2.5" if payload["over_2_5"] >= payload["under_2_5"] else "Under 2.5"


def build_match_receipt(
    outcome: Any,
    winner_payload: dict[str, Any] | None,
    goals_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    """Assemble one receipt from an outcome + its latest prediction payloads."""
    home, away = outcome.home_team, outcome.away_team
    total_goals = outcome.ft_home + outcome.ft_away

    receipt: dict[str, Any] = {
        "fixture_id": outcome.fixture_id,
        "kickoff": outcome.kickoff_at.isoformat(),
        "round": outcome.round,
        "home_team": home,
        "away_team": away,
        "final_score": f"{outcome.ft_home}-{outcome.ft_away}",
        "is_friendly": is_friendly(outcome.kickoff_at),
    }

    # ── Winner ──
    if winner_payload is not None:
        pick = _winner_pick(winner_payload, home, away)
        actual = _winner_actual(outcome.ft_home, outcome.ft_away, home, away)
        receipt["winner_pick"] = pick
        receipt["winner_actual"] = actual
        receipt["winner_correct"] = pick == actual
    else:
        receipt["winner_pick"] = None
        receipt["winner_actual"] = None
        receipt["winner_correct"] = None

    # ── Total goals (over/under 2.5) ──
    if goals_payload is not None:
        gpick = _goals_pick(goals_payload)
        actual_over = total_goals > GOALS_LINE
        receipt["goals_pick"] = gpick
        receipt["goals_actual"] = total_goals
        receipt["goals_correct"] = (gpick == "Over 2.5") == actual_over
    else:
        receipt["goals_pick"] = None
        receipt["goals_actual"] = total_goals
        receipt["goals_correct"] = None

    return receipt
