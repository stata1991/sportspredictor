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
