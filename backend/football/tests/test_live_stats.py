"""Tests for live match statistics boundary normalization (STATS-A)."""

from __future__ import annotations

from backend.football.live_stats import (
    FixtureStatistics,
    TeamMatchStatistics,
    normalize_fixture_statistics,
)

HOME_ID = 6
AWAY_ID = 25


def _stat(type_: str, value):
    return {"type": type_, "value": value}


def _block(team_id: int, name: str, stats: list[dict]):
    return {"team": {"id": team_id, "name": name}, "statistics": stats}


def _full_home_block(**overrides):
    stats = [
        _stat("Ball Possession", "65%"),
        _stat("Total Shots", 12),
        _stat("Shots on Goal", 5),
        _stat("Corner Kicks", 7),
        _stat("Fouls", 9),
        _stat("Yellow Cards", 2),
        _stat("Red Cards", 0),
        _stat("Goalkeeper Saves", 3),
    ]
    return _block(HOME_ID, "Brazil", stats)


def _full_away_block():
    stats = [
        _stat("Ball Possession", "35%"),
        _stat("Total Shots", 6),
        _stat("Shots on Goal", 2),
        _stat("Corner Kicks", 3),
        _stat("Fouls", 14),
        _stat("Yellow Cards", 3),
        _stat("Red Cards", 1),
        _stat("Goalkeeper Saves", 4),
    ]
    return _block(AWAY_ID, "Germany", stats)


# ── Possession string parsing ────────────────────────────────────────


class TestPossessionParsing:
    def test_percent_string_parsed_to_int(self):
        raw = [_full_home_block(), _full_away_block()]
        result = normalize_fixture_statistics(raw, HOME_ID, AWAY_ID)
        assert result is not None
        assert result.home.possession == 65
        assert result.away.possession == 35
        # Type is a plain int, not a "65%" string.
        assert isinstance(result.home.possession, int)

    def test_possession_none_when_missing(self):
        raw = [
            _block(HOME_ID, "Brazil", [_stat("Total Shots", 4)]),
            _block(AWAY_ID, "Germany", [_stat("Total Shots", 2)]),
        ]
        result = normalize_fixture_statistics(raw, HOME_ID, AWAY_ID)
        assert result is not None
        assert result.home.possession is None

    def test_possession_bare_int_tolerated(self):
        raw = [
            _block(HOME_ID, "Brazil", [_stat("Ball Possession", 60)]),
            _block(AWAY_ID, "Germany", [_stat("Ball Possession", 40)]),
        ]
        result = normalize_fixture_statistics(raw, HOME_ID, AWAY_ID)
        assert result.home.possession == 60
        assert result.away.possession == 40

    def test_possession_garbage_value_is_none_not_crash(self):
        raw = [
            _block(HOME_ID, "Brazil", [_stat("Ball Possession", "N/A")]),
            _block(AWAY_ID, "Germany", [_stat("Ball Possession", None)]),
        ]
        result = normalize_fixture_statistics(raw, HOME_ID, AWAY_ID)
        assert result.home.possession is None
        assert result.away.possession is None


# ── Missing types → None, never crash ────────────────────────────────


class TestMissingTypes:
    def test_missing_stat_type_is_none(self):
        # Only possession present; everything else should be None.
        raw = [
            _block(HOME_ID, "Brazil", [_stat("Ball Possession", "55%")]),
            _block(AWAY_ID, "Germany", [_stat("Ball Possession", "45%")]),
        ]
        result = normalize_fixture_statistics(raw, HOME_ID, AWAY_ID)
        assert result.home.shots_total is None
        assert result.home.shots_on_goal is None
        assert result.home.corners is None
        assert result.home.fouls is None
        assert result.home.yellow_cards is None
        assert result.home.red_cards is None
        assert result.home.goalkeeper_saves is None

    def test_null_value_becomes_none(self):
        raw = [
            _block(HOME_ID, "Brazil", [_stat("Total Shots", None)]),
            _block(AWAY_ID, "Germany", [_stat("Total Shots", 3)]),
        ]
        result = normalize_fixture_statistics(raw, HOME_ID, AWAY_ID)
        assert result.home.shots_total is None
        assert result.away.shots_total == 3

    def test_empty_statistics_list_all_none(self):
        raw = [
            _block(HOME_ID, "Brazil", []),
            _block(AWAY_ID, "Germany", []),
        ]
        result = normalize_fixture_statistics(raw, HOME_ID, AWAY_ID)
        assert result is not None
        assert result.home == TeamMatchStatistics()
        assert result.away == TeamMatchStatistics()

    def test_int_as_string_coerced(self):
        raw = [
            _block(HOME_ID, "Brazil", [_stat("Corner Kicks", "8")]),
            _block(AWAY_ID, "Germany", [_stat("Corner Kicks", "1")]),
        ]
        result = normalize_fixture_statistics(raw, HOME_ID, AWAY_ID)
        assert result.home.corners == 8
        assert result.away.corners == 1


# ── Order independence + team association ─────────────────────────────


class TestOrderAndAssociation:
    def test_unguaranteed_array_order_resolved_by_team_id(self):
        # Away block FIRST in the array — association must still be correct.
        raw = [_full_away_block(), _full_home_block()]
        result = normalize_fixture_statistics(raw, HOME_ID, AWAY_ID)
        assert result.home.possession == 65   # Brazil
        assert result.away.possession == 35   # Germany
        assert result.home.shots_total == 12
        assert result.away.shots_total == 6

    def test_unguaranteed_stat_order_extracted_by_type(self):
        # Shuffle the per-team stat list; extraction is by type name.
        shuffled = _block(
            HOME_ID,
            "Brazil",
            [
                _stat("Red Cards", 1),
                _stat("Ball Possession", "70%"),
                _stat("Goalkeeper Saves", 9),
                _stat("Total Shots", 15),
            ],
        )
        raw = [shuffled, _full_away_block()]
        result = normalize_fixture_statistics(raw, HOME_ID, AWAY_ID)
        assert result.home.possession == 70
        assert result.home.red_cards == 1
        assert result.home.goalkeeper_saves == 9
        assert result.home.shots_total == 15

    def test_only_one_team_block_present(self):
        # Feed sometimes returns a single block early; missing side → all None.
        raw = [_full_home_block()]
        result = normalize_fixture_statistics(raw, HOME_ID, AWAY_ID)
        assert result is not None
        assert result.home.possession == 65
        assert result.away == TeamMatchStatistics()


# ── Empty / unusable input → None ────────────────────────────────────


class TestEmptyInput:
    def test_empty_array_returns_none(self):
        assert normalize_fixture_statistics([], HOME_ID, AWAY_ID) is None

    def test_neither_team_matches_returns_none(self):
        raw = [
            _block(999, "X", [_stat("Total Shots", 1)]),
            _block(888, "Y", [_stat("Total Shots", 1)]),
        ]
        assert normalize_fixture_statistics(raw, HOME_ID, AWAY_ID) is None

    def test_malformed_block_does_not_crash(self):
        raw = [
            "not a dict",  # type: ignore[list-item]
            _full_home_block(),
            {"team": None, "statistics": None},
        ]
        result = normalize_fixture_statistics(raw, HOME_ID, AWAY_ID)
        assert result is not None
        assert result.home.possession == 65

    def test_result_is_json_serializable(self):
        raw = [_full_home_block(), _full_away_block()]
        result = normalize_fixture_statistics(raw, HOME_ID, AWAY_ID)
        assert isinstance(result, FixtureStatistics)
        dumped = result.model_dump(mode="json")
        assert dumped["home"]["possession"] == 65
        assert dumped["away"]["red_cards"] == 1
