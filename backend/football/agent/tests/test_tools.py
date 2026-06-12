"""Tests for the football agent tool implementations.

Uses synthetic AF* model objects and a mock APIFootballClient — does NOT
hit any real API.  Each tool execution function is tested in isolation.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from backend.football.agent.tools import (
    TOOL_DEFINITIONS,
    _exec_get_head_to_head,
    _exec_get_market_consensus,
    _exec_get_team_form,
    execute_tool,
)
from backend.football.schemas import (
    AFBookmaker,
    AFBet,
    AFFixture,
    AFFixtureInfo,
    AFFixtureStatus,
    AFGoals,
    AFLeagueRef,
    AFOddValue,
    AFOdds,
    AFScore,
    AFTeam,
    AFTeams,
    AFVenue,
)


# ── Helpers ──────────────────────────────────────────────────────────


def _make_fixture(
    home_name: str = "Brazil",
    away_name: str = "Germany",
    home_id: int = 6,
    away_id: int = 25,
    home_goals: int | None = 2,
    away_goals: int | None = 1,
    status: str = "FT",
    date: str = "2026-06-15T18:00:00+00:00",
) -> AFFixture:
    """Build a synthetic AFFixture."""
    return AFFixture(
        fixture=AFFixtureInfo(
            id=1001,
            timezone="UTC",
            date=datetime.fromisoformat(date),
            timestamp=int(datetime.fromisoformat(date).timestamp()),
            venue=AFVenue(),
            status=AFFixtureStatus(long="Match Finished", short=status),
        ),
        league=AFLeagueRef(id=1, name="World Cup", season=2026),
        teams=AFTeams(
            home=AFTeam(id=home_id, name=home_name),
            away=AFTeam(id=away_id, name=away_name),
        ),
        goals=AFGoals(home=home_goals, away=away_goals),
        score=AFScore(),
    )


def _make_odds(
    home_odd: str = "1.80",
    draw_odd: str = "3.50",
    away_odd: str = "4.50",
) -> AFOdds:
    """Build a synthetic AFOdds with one bookmaker."""
    return AFOdds(
        bookmakers=[
            AFBookmaker(
                id=1,
                name="TestBookie",
                bets=[
                    AFBet(
                        id=1,
                        name="Match Winner",
                        values=[
                            AFOddValue(value="Home", odd=home_odd),
                            AFOddValue(value="Draw", odd=draw_odd),
                            AFOddValue(value="Away", odd=away_odd),
                        ],
                    )
                ],
            )
        ]
    )


def _mock_client() -> AsyncMock:
    """Create a mock APIFootballClient."""
    return AsyncMock()


# ── Tool definitions ─────────────────────────────────────────────────


class TestToolDefinitions:
    def test_three_tools_defined(self):
        assert len(TOOL_DEFINITIONS) == 3

    def test_all_have_required_keys(self):
        for tool in TOOL_DEFINITIONS:
            assert "name" in tool
            assert "description" in tool
            assert "input_schema" in tool

    def test_tool_names(self):
        names = {t["name"] for t in TOOL_DEFINITIONS}
        assert names == {
            "get_team_form",
            "get_head_to_head",
            "get_market_consensus",
        }

    def test_no_injuries_tool(self):
        """No injuries coverage for WC 2026 — the tool must not exist."""
        names = {t["name"] for t in TOOL_DEFINITIONS}
        assert "get_injuries" not in names

    def test_input_schemas_are_valid_objects(self):
        for tool in TOOL_DEFINITIONS:
            schema = tool["input_schema"]
            assert schema["type"] == "object"
            assert "properties" in schema
            assert "required" in schema


# ── get_team_form ────────────────────────────────────────────────────


class TestGetTeamForm:
    @pytest.mark.asyncio
    async def test_returns_form_summary(self):
        client = _mock_client()
        client.get_team_last_fixtures.return_value = [
            _make_fixture(home_goals=2, away_goals=1),
            _make_fixture(home_goals=0, away_goals=0, status="FT"),
            _make_fixture(home_goals=1, away_goals=3),
        ]

        result = await _exec_get_team_form(
            client, {"team_id": 6, "team_name": "Brazil", "last": 5}
        )

        assert "Brazil" in result
        assert "Recent form" in result
        client.get_team_last_fixtures.assert_called_once_with(6, last=5)

    @pytest.mark.asyncio
    async def test_empty_fixtures(self):
        client = _mock_client()
        client.get_team_last_fixtures.return_value = []

        result = await _exec_get_team_form(
            client, {"team_id": 6, "team_name": "Brazil"}
        )

        assert "No recent fixtures" in result

    @pytest.mark.asyncio
    async def test_caps_last_at_10(self):
        client = _mock_client()
        client.get_team_last_fixtures.return_value = []

        await _exec_get_team_form(
            client, {"team_id": 6, "team_name": "Brazil", "last": 50}
        )

        client.get_team_last_fixtures.assert_called_once_with(6, last=10)

    @pytest.mark.asyncio
    async def test_win_draw_loss_counting(self):
        client = _mock_client()
        # Team 6 (Brazil) is home, wins 2-1.
        client.get_team_last_fixtures.return_value = [
            _make_fixture(home_id=6, home_goals=2, away_goals=1),
            _make_fixture(home_id=6, home_goals=0, away_goals=0),
        ]

        result = await _exec_get_team_form(
            client, {"team_id": 6, "team_name": "Brazil"}
        )

        assert "1W 1D 0L" in result


# ── get_head_to_head ─────────────────────────────────────────────────


class TestGetHeadToHead:
    @pytest.mark.asyncio
    async def test_returns_h2h_summary(self):
        client = _mock_client()
        client.get_head_to_head.return_value = [
            _make_fixture(home_id=6, away_id=25, home_goals=2, away_goals=1),
            _make_fixture(home_id=25, away_id=6, home_goals=0, away_goals=1),
        ]

        result = await _exec_get_head_to_head(
            client,
            {"home_team_id": 6, "away_team_id": 25},
        )

        assert "Head-to-head" in result
        client.get_head_to_head.assert_called_once_with(6, 25, last=10)

    @pytest.mark.asyncio
    async def test_empty_h2h(self):
        client = _mock_client()
        client.get_head_to_head.return_value = []

        result = await _exec_get_head_to_head(
            client,
            {"home_team_id": 6, "away_team_id": 25},
        )

        assert "No head-to-head" in result


# ── get_market_consensus ─────────────────────────────────────────────


class TestGetMarketConsensus:
    @pytest.mark.asyncio
    async def test_returns_implied_probabilities(self):
        client = _mock_client()
        client.get_odds.return_value = [_make_odds("1.80", "3.50", "4.50")]

        result = await _exec_get_market_consensus(
            client, {"fixture_id": 1001}
        )

        assert "Market consensus" in result
        assert "Implied probs" in result
        assert "1 bookmakers" in result

    @pytest.mark.asyncio
    async def test_no_odds(self):
        client = _mock_client()
        client.get_odds.return_value = []

        result = await _exec_get_market_consensus(
            client, {"fixture_id": 1001}
        )

        assert "No odds available" in result

    @pytest.mark.asyncio
    async def test_no_1x2_bets(self):
        client = _mock_client()
        # Odds exist but no Match Winner bet.
        client.get_odds.return_value = [
            AFOdds(
                bookmakers=[
                    AFBookmaker(
                        id=1,
                        name="TestBookie",
                        bets=[
                            AFBet(id=2, name="Over/Under", values=[]),
                        ],
                    )
                ]
            )
        ]

        result = await _exec_get_market_consensus(
            client, {"fixture_id": 1001}
        )

        assert "No 1X2 odds" in result

    @pytest.mark.asyncio
    async def test_multiple_bookmakers_averaged(self):
        client = _mock_client()
        client.get_odds.return_value = [
            AFOdds(
                bookmakers=[
                    AFBookmaker(
                        id=1,
                        name="Bookie1",
                        bets=[
                            AFBet(
                                id=1,
                                name="Match Winner",
                                values=[
                                    AFOddValue(value="Home", odd="2.00"),
                                    AFOddValue(value="Draw", odd="3.00"),
                                    AFOddValue(value="Away", odd="4.00"),
                                ],
                            )
                        ],
                    ),
                    AFBookmaker(
                        id=2,
                        name="Bookie2",
                        bets=[
                            AFBet(
                                id=1,
                                name="Match Winner",
                                values=[
                                    AFOddValue(value="Home", odd="2.20"),
                                    AFOddValue(value="Draw", odd="3.20"),
                                    AFOddValue(value="Away", odd="3.80"),
                                ],
                            )
                        ],
                    ),
                ]
            )
        ]

        result = await _exec_get_market_consensus(
            client, {"fixture_id": 1001}
        )

        assert "2 bookmakers" in result


# ── execute_tool dispatch ────────────────────────────────────────────


class TestExecuteTool:
    @pytest.mark.asyncio
    async def test_dispatches_known_tool(self):
        client = _mock_client()
        client.get_head_to_head.return_value = []

        result = await execute_tool(
            client, "get_head_to_head",
            {"home_team_id": 6, "away_team_id": 25},
        )

        assert "No head-to-head" in result

    @pytest.mark.asyncio
    async def test_unknown_tool_raises_keyerror(self):
        client = _mock_client()

        with pytest.raises(KeyError):
            await execute_tool(client, "nonexistent_tool", {})

    @pytest.mark.asyncio
    async def test_get_injuries_no_longer_dispatchable(self):
        """get_injuries was removed — dispatching it must fail."""
        client = _mock_client()

        with pytest.raises(KeyError):
            await execute_tool(client, "get_injuries", {})


# ── Client parse_result ──────────────────────────────────────────────


class TestParseResult:
    """Test the static _parse_result method on AnthropicAgentClient."""

    def _parse(self, text: str):
        from backend.football.agent.client import AnthropicAgentClient

        return AnthropicAgentClient._parse_result(text)

    def _valid_json(self, **overrides) -> str:
        """Build a valid JSON string, with optional field overrides."""
        data = {
            "paragraphs": [
                "Paragraph 1 numbers story.",
                "Paragraph 2 context.",
                "Paragraph 3 honest hedge.",
            ],
            "claims": [
                {"text": "Won 4 of 5", "source": "get_team_form"},
            ],
            "upset_index": 0.35,
            "upset_signals": [
                {"signal": "Form", "direction": "increases", "source": "get_team_form"},
            ],
            "upset_paths": ["Path A", "Path B", "Path C"],
        }
        data.update(overrides)
        return json.dumps(data)

    def test_valid_full_schema(self):
        result = self._parse(self._valid_json())
        assert len(result.paragraphs) == 3
        assert result.paragraphs[0] == "Paragraph 1 numbers story."
        assert result.upset_index == 0.35
        assert len(result.claims) == 1
        assert result.claims[0].text == "Won 4 of 5"
        assert result.claims[0].source == "get_team_form"
        assert len(result.upset_signals) == 1
        assert result.upset_paths == ["Path A", "Path B", "Path C"]

    def test_empty_upset_paths_valid(self):
        """upset_paths=[] is valid for non-dominant favourites."""
        result = self._parse(self._valid_json(upset_paths=[]))
        assert result.upset_paths == []

    def test_strips_markdown_fencing(self):
        raw = "```json\n" + self._valid_json() + "\n```"
        result = self._parse(raw)
        assert len(result.paragraphs) == 3

    def test_clamps_upset_index_high(self):
        result = self._parse(self._valid_json(upset_index=1.5))
        assert result.upset_index == 1.0

    def test_clamps_upset_index_negative(self):
        result = self._parse(self._valid_json(upset_index=-0.2))
        assert result.upset_index == 0.0

    def test_missing_paragraphs_raises(self):
        from backend.football.agent.client import AgentParseError

        raw = self._valid_json()
        data = json.loads(raw)
        del data["paragraphs"]
        with pytest.raises(AgentParseError, match="paragraphs"):
            self._parse(json.dumps(data))

    def test_wrong_paragraph_count_raises(self):
        from backend.football.agent.client import AgentParseError

        with pytest.raises(AgentParseError, match="exactly 3"):
            self._parse(self._valid_json(paragraphs=["Only one."]))

    def test_missing_claims_raises(self):
        from backend.football.agent.client import AgentParseError

        raw = self._valid_json()
        data = json.loads(raw)
        del data["claims"]
        with pytest.raises(AgentParseError, match="claims"):
            self._parse(json.dumps(data))

    def test_claim_missing_source_raises(self):
        from backend.football.agent.client import AgentParseError

        with pytest.raises(AgentParseError, match="source"):
            self._parse(self._valid_json(claims=[{"text": "Fact"}]))

    def test_missing_upset_index_raises(self):
        from backend.football.agent.client import AgentParseError

        raw = self._valid_json()
        data = json.loads(raw)
        del data["upset_index"]
        with pytest.raises(AgentParseError, match="upset_index"):
            self._parse(json.dumps(data))

    def test_missing_upset_signals_raises(self):
        from backend.football.agent.client import AgentParseError

        raw = self._valid_json()
        data = json.loads(raw)
        del data["upset_signals"]
        with pytest.raises(AgentParseError, match="upset_signals"):
            self._parse(json.dumps(data))

    def test_upset_paths_wrong_count_raises(self):
        from backend.football.agent.client import AgentParseError

        with pytest.raises(AgentParseError, match="0 or 3"):
            self._parse(self._valid_json(upset_paths=["Only one."]))

    def test_invalid_json_raises(self):
        from backend.football.agent.client import AgentParseError

        with pytest.raises(AgentParseError, match="Invalid JSON"):
            self._parse("not json at all")

    def test_empty_paragraph_raises(self):
        from backend.football.agent.client import AgentParseError

        with pytest.raises(AgentParseError, match="paragraphs\\[1\\]"):
            self._parse(self._valid_json(
                paragraphs=["P1.", "", "P3."]
            ))


# ── Cost metrics ─────────────────────────────────────────────────────


class TestCostMetrics:
    def test_estimated_cost(self):
        from backend.football.agent.client import AgentCostMetrics

        cost = AgentCostMetrics(
            input_tokens=10_000,
            output_tokens=500,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=0,
        )
        # 10k input at $3/M = $0.03, 500 output at $15/M = $0.0075
        expected = 0.03 + 0.0075
        assert abs(cost.estimated_cost_usd - expected) < 1e-6

    def test_cache_costs(self):
        from backend.football.agent.client import AgentCostMetrics

        cost = AgentCostMetrics(
            input_tokens=0,
            output_tokens=0,
            cache_creation_input_tokens=1_000_000,
            cache_read_input_tokens=1_000_000,
        )
        # 1M cache write at $3.75/M + 1M cache read at $0.30/M = $4.05
        assert abs(cost.estimated_cost_usd - 4.05) < 1e-6
