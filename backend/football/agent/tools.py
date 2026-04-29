"""Anthropic tool definitions and implementations for the football agent.

Each tool wraps one or more APIFootballClient calls and returns a
plain-text summary suitable for Claude's context window.  Tool
definitions follow the Anthropic tool-use schema (name, description,
input_schema).

The agent calls these via the Anthropic messages API tool_use flow.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from backend.football.data_provider import APIFootballClient
from backend.football.schemas import AFFixture

logger = logging.getLogger(__name__)


# ── Tool definitions (Anthropic schema) ──────────────────────────────


TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "get_team_form",
        "description": (
            "Retrieve a team's recent form — last N fixtures with results "
            "and scores. Use this to assess current momentum and recent "
            "performance patterns."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "team_id": {
                    "type": "integer",
                    "description": "API-Football team ID.",
                },
                "team_name": {
                    "type": "string",
                    "description": "Team name (for display only).",
                },
                "last": {
                    "type": "integer",
                    "description": "Number of recent fixtures to retrieve (max 10).",
                    "default": 5,
                },
            },
            "required": ["team_id", "team_name"],
        },
    },
    {
        "name": "get_head_to_head",
        "description": (
            "Retrieve head-to-head history between two teams. Returns "
            "recent H2H fixtures with scores. Use this to identify "
            "historical dominance patterns."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "home_team_id": {
                    "type": "integer",
                    "description": "API-Football team ID for the home side.",
                },
                "away_team_id": {
                    "type": "integer",
                    "description": "API-Football team ID for the away side.",
                },
                "last": {
                    "type": "integer",
                    "description": "Number of H2H fixtures to retrieve (max 10).",
                    "default": 10,
                },
            },
            "required": ["home_team_id", "away_team_id"],
        },
    },
    {
        "name": "get_injuries",
        "description": (
            "Retrieve current injuries and suspensions for the tournament. "
            "Returns player name, injury type, and reason. Do NOT use "
            "player names in your written output — refer to them by "
            "position or role only (e.g. 'starting goalkeeper', "
            "'first-choice striker')."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_market_consensus",
        "description": (
            "Retrieve betting odds for a fixture from major bookmakers. "
            "Use this to gauge market consensus on match outcome. Returns "
            "average implied probabilities across bookmakers."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "fixture_id": {
                    "type": "integer",
                    "description": "API-Football fixture ID.",
                },
            },
            "required": ["fixture_id"],
        },
    },
]


# ── Tool implementations ─────────────────────────────────────────────


def _format_fixture_result(fx: AFFixture) -> str:
    """Format a single fixture into a one-line summary."""
    home = fx.teams.home.name
    away = fx.teams.away.name
    h_goals = fx.goals.home
    a_goals = fx.goals.away
    status = fx.fixture.status.short
    date = fx.fixture.date.strftime("%Y-%m-%d")

    if h_goals is not None and a_goals is not None:
        return f"{date}: {home} {h_goals}-{a_goals} {away} ({status})"
    return f"{date}: {home} vs {away} ({status})"


async def _exec_get_team_form(
    client: APIFootballClient,
    tool_input: dict[str, Any],
) -> str:
    """Execute get_team_form tool."""
    team_id = tool_input["team_id"]
    team_name = tool_input.get("team_name", f"Team {team_id}")
    last = min(tool_input.get("last", 5), 10)

    fixtures = await client.get_team_last_fixtures(team_id, last=last)

    if not fixtures:
        return f"No recent fixtures found for {team_name} (ID: {team_id})."

    lines = [f"Recent form for {team_name} (last {len(fixtures)} matches):"]
    wins, draws, losses = 0, 0, 0

    for fx in fixtures:
        lines.append(f"  {_format_fixture_result(fx)}")
        if fx.goals.home is not None and fx.goals.away is not None:
            is_home = fx.teams.home.id == team_id
            team_goals = fx.goals.home if is_home else fx.goals.away
            opp_goals = fx.goals.away if is_home else fx.goals.home
            if team_goals > opp_goals:
                wins += 1
            elif team_goals == opp_goals:
                draws += 1
            else:
                losses += 1

    lines.append(f"Summary: {wins}W {draws}D {losses}L")
    return "\n".join(lines)


async def _exec_get_head_to_head(
    client: APIFootballClient,
    tool_input: dict[str, Any],
) -> str:
    """Execute get_head_to_head tool."""
    home_id = tool_input["home_team_id"]
    away_id = tool_input["away_team_id"]
    last = min(tool_input.get("last", 10), 10)

    fixtures = await client.get_head_to_head(home_id, away_id, last=last)

    if not fixtures:
        return "No head-to-head fixtures found between these teams."

    lines = [f"Head-to-head record (last {len(fixtures)} meetings):"]
    home_wins, draws, away_wins = 0, 0, 0

    # Use first fixture to resolve team names.
    team_a_name = fixtures[0].teams.home.name
    team_b_name = fixtures[0].teams.away.name

    for fx in fixtures:
        lines.append(f"  {_format_fixture_result(fx)}")
        if fx.goals.home is not None and fx.goals.away is not None:
            if fx.goals.home > fx.goals.away:
                if fx.teams.home.id == home_id:
                    home_wins += 1
                else:
                    away_wins += 1
            elif fx.goals.home < fx.goals.away:
                if fx.teams.away.id == home_id:
                    home_wins += 1
                else:
                    away_wins += 1
            else:
                draws += 1

    lines.append(
        f"Summary: Team {home_id} wins: {home_wins}, "
        f"Draws: {draws}, Team {away_id} wins: {away_wins}"
    )
    return "\n".join(lines)


async def _exec_get_injuries(
    client: APIFootballClient,
    tool_input: dict[str, Any],
) -> str:
    """Execute get_injuries tool."""
    injuries = await client.get_injuries()

    if not injuries:
        return "No injuries or suspensions currently reported for this tournament."

    # Group by team.
    by_team: dict[str, list[str]] = {}
    for inj in injuries:
        team = inj.team.name
        player_type = inj.player.type or "Unknown"
        reason = inj.player.reason or "unspecified"
        entry = f"{inj.player.name} — {player_type}: {reason}"
        by_team.setdefault(team, []).append(entry)

    lines = [f"Injuries/suspensions ({len(injuries)} total):"]
    for team, entries in sorted(by_team.items()):
        lines.append(f"  {team}:")
        for e in entries:
            lines.append(f"    - {e}")

    return "\n".join(lines)


async def _exec_get_market_consensus(
    client: APIFootballClient,
    tool_input: dict[str, Any],
) -> str:
    """Execute get_market_consensus tool."""
    fixture_id = tool_input["fixture_id"]
    odds_list = await client.get_odds(fixture_id)

    if not odds_list:
        return f"No odds available for fixture {fixture_id}."

    # Extract 1X2 (match winner) odds from all bookmakers.
    home_odds: list[float] = []
    draw_odds: list[float] = []
    away_odds: list[float] = []

    for odds_item in odds_list:
        for bm in odds_item.bookmakers:
            for bet in bm.bets:
                if bet.name.lower() in ("match winner", "1x2"):
                    for val in bet.values:
                        try:
                            odd = float(val.odd)
                        except (ValueError, TypeError):
                            continue
                        label = val.value.lower()
                        if label == "home":
                            home_odds.append(odd)
                        elif label == "draw":
                            draw_odds.append(odd)
                        elif label == "away":
                            away_odds.append(odd)

    if not home_odds:
        return f"No 1X2 odds found for fixture {fixture_id}."

    def _avg(values: list[float]) -> float:
        return sum(values) / len(values) if values else 0.0

    avg_home = _avg(home_odds)
    avg_draw = _avg(draw_odds)
    avg_away = _avg(away_odds)

    # Convert to implied probabilities (normalised).
    raw_sum = (1 / avg_home) + (1 / avg_draw) + (1 / avg_away)
    p_home = (1 / avg_home) / raw_sum
    p_draw = (1 / avg_draw) / raw_sum
    p_away = (1 / avg_away) / raw_sum

    lines = [
        f"Market consensus for fixture {fixture_id} "
        f"({len(home_odds)} bookmakers):",
        f"  Average odds: Home {avg_home:.2f} | Draw {avg_draw:.2f} | Away {avg_away:.2f}",
        f"  Implied probs: Home {p_home:.1%} | Draw {p_draw:.1%} | Away {p_away:.1%}",
    ]
    return "\n".join(lines)


# ── Dispatch ─────────────────────────────────────────────────────────

_TOOL_DISPATCH: dict[
    str,
    Any,  # async callable(APIFootballClient, dict) -> str
] = {
    "get_team_form": _exec_get_team_form,
    "get_head_to_head": _exec_get_head_to_head,
    "get_injuries": _exec_get_injuries,
    "get_market_consensus": _exec_get_market_consensus,
}


async def execute_tool(
    client: APIFootballClient,
    tool_name: str,
    tool_input: dict[str, Any],
) -> str:
    """Execute a named tool and return the text result.

    Raises ``KeyError`` for unknown tool names.  All exceptions from
    the underlying API client propagate to the caller.
    """
    handler = _TOOL_DISPATCH[tool_name]
    result = await handler(client, tool_input)
    logger.info(
        "Tool %s executed (input_keys=%s, result_len=%d)",
        tool_name,
        list(tool_input.keys()),
        len(result),
    )
    return result
