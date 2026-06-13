"""Live match statistics — boundary normalization (STATS-A).

API-Football ``/fixtures/statistics?fixture={id}`` returns a 2-element
array (one block per team), each with a ``statistics`` list of
``{type, value}`` pairs. Quirks this module absorbs at the boundary so
nothing downstream has to:

- ``"Ball Possession"`` is a STRING like ``"65%"``; the rest are ints
  (or ``null`` before a stat populates early in the match).
- The two team blocks are NOT in a guaranteed home-then-away order —
  association is resolved by team id, never by array index.
- Stat ``type`` strings may be absent entirely (early minutes, before
  stats populate). Missing → ``None``, never a crash.

Display-only. This module makes no claim about who is "winning"; it just
shapes raw numbers for the UI to render.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)


# API-Football stat ``type`` string → our normalized field name.
# Only the stats STATS-A displays are mapped; everything else is ignored.
STAT_TYPE_FIELDS: dict[str, str] = {
    "Ball Possession": "possession",
    "Total Shots": "shots_total",
    "Shots on Goal": "shots_on_goal",
    "Corner Kicks": "corners",
    "Fouls": "fouls",
    "Yellow Cards": "yellow_cards",
    "Red Cards": "red_cards",
    "Goalkeeper Saves": "goalkeeper_saves",
}


class TeamMatchStatistics(BaseModel):
    """One team's in-play stats, parsed into named, order-independent fields.

    Every field is nullable: a stat that has not populated yet (early in
    the match) or is absent from the feed normalizes to ``None`` rather
    than ``0`` — so the UI can omit it instead of showing a fake zero.
    """

    model_config = ConfigDict(extra="forbid")

    possession: int | None = None       # parsed from "65%" → 65
    shots_total: int | None = None
    shots_on_goal: int | None = None
    corners: int | None = None
    fouls: int | None = None
    yellow_cards: int | None = None
    red_cards: int | None = None
    goalkeeper_saves: int | None = None


class FixtureStatistics(BaseModel):
    """Home/away in-play statistics for a single fixture."""

    model_config = ConfigDict(extra="forbid")

    home: TeamMatchStatistics
    away: TeamMatchStatistics


def _parse_possession(value: Any) -> int | None:
    """Parse a possession value (``"65%"`` or ``65``) into an int percent.

    Tolerates a missing/None value, a bare int, or a ``"65%"`` string.
    Anything unparseable → ``None`` (never raises).
    """
    if value is None:
        return None
    if isinstance(value, bool):  # guard: bool is an int subclass
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        cleaned = value.strip().rstrip("%").strip()
        try:
            return int(float(cleaned))
        except (ValueError, TypeError):
            return None
    return None


def _parse_int(value: Any) -> int | None:
    """Coerce an integer-ish stat value to int. Missing/None/unparseable → None."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return None
        try:
            return int(float(cleaned))
        except (ValueError, TypeError):
            return None
    return None


def _team_block_to_stats(block: dict[str, Any]) -> TeamMatchStatistics:
    """Normalize one team's raw statistics block into named fields.

    Builds a ``{type: value}`` lookup first so extraction is by type name,
    not array position — the feed does not guarantee stat ordering.
    """
    raw_list = block.get("statistics") or []
    by_type: dict[str, Any] = {}
    for item in raw_list:
        if not isinstance(item, dict):
            continue
        stat_type = item.get("type")
        if isinstance(stat_type, str):
            by_type[stat_type] = item.get("value")

    return TeamMatchStatistics(
        possession=_parse_possession(by_type.get("Ball Possession")),
        shots_total=_parse_int(by_type.get("Total Shots")),
        shots_on_goal=_parse_int(by_type.get("Shots on Goal")),
        corners=_parse_int(by_type.get("Corner Kicks")),
        fouls=_parse_int(by_type.get("Fouls")),
        yellow_cards=_parse_int(by_type.get("Yellow Cards")),
        red_cards=_parse_int(by_type.get("Red Cards")),
        goalkeeper_saves=_parse_int(by_type.get("Goalkeeper Saves")),
    )


def normalize_fixture_statistics(
    raw: list[dict[str, Any]],
    home_team_id: int,
    away_team_id: int,
) -> FixtureStatistics | None:
    """Normalize the raw 2-block stats array into home/away named stats.

    Association is by team id, so a feed that returns the away block first
    is handled correctly. Returns ``None`` when stats have not populated
    yet (empty array, or neither team block matches) — the caller treats
    that as "stats coming in", not as zeros.

    Never raises on shape quirks: a malformed block degrades to all-``None``
    fields for that side rather than propagating an error.
    """
    if not raw:
        return None

    home_block: dict[str, Any] | None = None
    away_block: dict[str, Any] | None = None

    for block in raw:
        if not isinstance(block, dict):
            continue
        team = block.get("team") or {}
        team_id = team.get("id") if isinstance(team, dict) else None
        if team_id == home_team_id:
            home_block = block
        elif team_id == away_team_id:
            away_block = block

    # If neither side resolved, stats are not usable for this fixture.
    if home_block is None and away_block is None:
        return None

    return FixtureStatistics(
        home=(
            _team_block_to_stats(home_block)
            if home_block is not None
            else TeamMatchStatistics()
        ),
        away=(
            _team_block_to_stats(away_block)
            if away_block is not None
            else TeamMatchStatistics()
        ),
    )


# ── Lean signal (STATS-B; engine-owned, deterministic) ───────────────
#
# A code-computed read of which side the in-play numbers lean toward.
# THIS IS THE ENGINE'S JOB, NOT THE LLM'S — the narration model is later
# handed this result and only narrates it; it never decides who is on top.
#
# Formula: a signed weighted sum of home-minus-away differentials over the
# four most threat-indicative stats. Positive → home; negative → away;
# inside a dead-band around zero → "even". Weights below; a metric only
# contributes when BOTH sides have a value (early-match nulls are skipped,
# so the lean stays "even" until real numbers arrive).

LEAN_WEIGHTS: dict[str, float] = {
    "shots_on_goal": 1.0,   # clearest single threat signal
    "shots_total": 0.3,     # volume of attacking intent
    "possession": 0.03,     # per percentage point (a 20-pt edge ≈ 0.6)
    "corners": 0.15,        # sustained territorial pressure
}

# |score| must exceed this to lean off "even". Tuned so a lone one-shot-on-
# goal edge with nothing else (score 1.0) stays "even" — a real lean needs
# corroborating signal, which damps tick-to-tick flicker into LEAN-CROSS.
LEAN_THRESHOLD: float = 1.0


@dataclass(frozen=True)
class LeanSignal:
    """Deterministic read of which side the live stats favour."""

    leaning_side: str   # "home" | "away" | "even"
    score: float        # signed weighted sum; >0 home, <0 away
    contributing: int   # metrics with both sides present (0 → forced "even")


def compute_lean(stats: FixtureStatistics | None) -> LeanSignal:
    """Compute the engine lean from normalized stats. Pure + deterministic.

    Returns ``LeanSignal("even", 0.0, 0)`` when stats are absent or no
    metric has both sides populated — the lean never guesses from nothing.
    """
    if stats is None:
        return LeanSignal("even", 0.0, 0)

    score = 0.0
    contributing = 0
    for field, weight in LEAN_WEIGHTS.items():
        home_val = getattr(stats.home, field)
        away_val = getattr(stats.away, field)
        if home_val is None or away_val is None:
            continue
        score += weight * (home_val - away_val)
        contributing += 1

    if contributing == 0:
        return LeanSignal("even", 0.0, 0)

    if score > LEAN_THRESHOLD:
        side = "home"
    elif score < -LEAN_THRESHOLD:
        side = "away"
    else:
        side = "even"
    return LeanSignal(leaning_side=side, score=round(score, 3), contributing=contributing)


def favoured_side(p_home_win: float, p_away_win: float) -> str:
    """The live probability bar's favoured side (draw ignored for 'side')."""
    if p_home_win > p_away_win:
        return "home"
    if p_away_win > p_home_win:
        return "away"
    return "even"


def lean_agrees_with_prediction(leaning_side: str, fav_side: str) -> bool:
    """Whether the stat lean agrees with the favourite.

    An "even" lean never contradicts the favourite (no tension to surface).
    A concrete lean agrees only when it matches the favoured side.
    """
    if leaning_side == "even":
        return True
    return leaning_side == fav_side
