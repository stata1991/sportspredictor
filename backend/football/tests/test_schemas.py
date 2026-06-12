"""Parsing tests for API-Football Pydantic models.

Uses real (or realistic) API-Football response samples so schema bugs
surface here rather than inside the data provider.
"""

from __future__ import annotations

from backend.football.schemas import (
    AFCoverage,
    AFFixture,
    AFLineup,
    AFTeam,
    CoverageStatus,
)

# ── Real fixture response sample (Mexico vs South Africa, 1489369) ───

_FIXTURE_RESPONSE_ITEM: dict = {
    "fixture": {
        "id": 1489369,
        "referee": None,
        "timezone": "UTC",
        "date": "2026-06-11T18:00:00+00:00",
        "timestamp": 1781366400,
        "periods": {"first": None, "second": None},
        "venue": {
            "id": 392,
            "name": "Estadio Azteca",
            "city": "Ciudad de México",
        },
        "status": {"long": "Not Started", "short": "NS", "elapsed": None, "extra": None},
    },
    "league": {
        "id": 1,
        "name": "World Cup",
        "country": "World",
        "logo": "https://media.api-sports.io/football/leagues/1.png",
        "flag": None,
        "season": 2026,
        "round": "Group A - 1",
    },
    "teams": {
        "home": {
            "id": 16,
            "name": "Mexico",
            "logo": "https://media.api-sports.io/football/teams/16.png",
            "winner": None,
        },
        "away": {
            "id": 15,
            "name": "South Africa",
            "logo": "https://media.api-sports.io/football/teams/15.png",
            "winner": None,
        },
    },
    "goals": {"home": None, "away": None},
    "score": {
        "halftime": {"home": None, "away": None},
        "fulltime": {"home": None, "away": None},
        "extratime": {"home": None, "away": None},
        "penalty": {"home": None, "away": None},
    },
}


def test_af_fixture_parses_real_response() -> None:
    """Parse a real fixture response item into AFFixture."""
    fx = AFFixture.model_validate(_FIXTURE_RESPONSE_ITEM)

    assert fx.fixture.id == 1489369
    assert fx.fixture.date.year == 2026
    assert fx.fixture.date.month == 6
    assert fx.fixture.date.day == 11
    assert fx.teams.home.name == "Mexico"
    assert fx.teams.away.name == "South Africa"
    assert fx.fixture.status.short == "NS"
    assert fx.score.halftime.home is None


def test_af_coverage_flattens_nested_fixtures() -> None:
    """Nested fixtures.* keys get hoisted to fixtures_* on the model."""
    raw = {
        "fixtures": {
            "events": True,
            "lineups": False,
            "statistics_fixtures": True,
            "statistics_players": False,
        },
        "standings": True,
        "predictions": True,
        "odds": False,
        "injuries": False,
        "players": False,
        "top_scorers": False,
        "top_assists": False,
        "top_cards": False,
    }
    cov = AFCoverage.model_validate(raw)

    assert cov.fixtures_events is True
    assert cov.fixtures_lineups is False
    assert cov.fixtures_statistics_fixtures is True
    assert cov.standings is True

    # The nested "fixtures" key should have been consumed by the
    # validator — it must not appear as a leftover attribute.
    assert not hasattr(cov, "fixtures")


def test_af_coverage_handles_missing_fixtures_subdict() -> None:
    """If the API omits the fixtures sub-dict, all fixtures_* default False."""
    raw = {
        "standings": True,
        "predictions": True,
        "odds": False,
        "injuries": False,
        "players": False,
        "top_scorers": False,
        "top_assists": False,
        "top_cards": False,
    }
    cov = AFCoverage.model_validate(raw)

    assert cov.fixtures_events is False
    assert cov.fixtures_lineups is False
    assert cov.fixtures_statistics_fixtures is False
    assert cov.fixtures_statistics_players is False


def test_coverage_status_warns_on_expected_gaps() -> None:
    """Current WC 2026 state (only standings+predictions true) → 1 warning."""
    cov = AFCoverage.model_validate({
        "fixtures": {
            "events": False,
            "lineups": False,
            "statistics_fixtures": False,
            "statistics_players": False,
        },
        "standings": True,
        "predictions": True,
        "odds": False,
        "injuries": False,
        "players": False,
        "top_scorers": False,
        "top_assists": False,
        "top_cards": False,
    })
    status = CoverageStatus.from_af_coverage(cov)

    assert len(status.warnings) == 1
    warning = status.warnings[0]
    for expected_key in [
        "fixtures_events",
        "fixtures_lineups",
        "fixtures_statistics_fixtures",
        "odds",
    ]:
        assert expected_key in warning

    # injuries=false is confirmed permanent for WC 2026 — no longer an
    # expected-coverage gap, so it must not be warned about.
    assert "injuries" not in warning


def test_coverage_status_no_warnings_when_complete() -> None:
    """All expected coverage flags true → no warnings."""
    cov = AFCoverage.model_validate({
        "fixtures": {
            "events": True,
            "lineups": True,
            "statistics_fixtures": True,
            "statistics_players": True,
        },
        "standings": True,
        "predictions": True,
        "odds": True,
        "injuries": True,
        "players": True,
        "top_scorers": True,
        "top_assists": True,
        "top_cards": True,
    })
    status = CoverageStatus.from_af_coverage(cov)

    assert status.warnings == []


def test_extra_fields_ignored() -> None:
    """Unknown fields are silently discarded (extra='ignore')."""
    team = AFTeam.model_validate({
        "id": 1,
        "name": "X",
        "logo": "y",
        "winner": None,
        "future_field": "anything",
    })
    assert team.id == 1
    assert team.name == "X"
    assert not hasattr(team, "future_field")


def test_af_lineup_player_wrapper() -> None:
    """startXI items are wrapped in {"player": ...} — verify parsing."""
    raw = {
        "team": {"id": 16, "name": "Mexico", "logo": "x.png", "winner": None},
        "formation": "4-3-3",
        "startXI": [
            {"player": {"id": 1, "name": "Foo", "number": 10, "pos": "G", "grid": "1:1"}},
        ],
        "substitutes": [],
        "coach": None,
    }
    lineup = AFLineup.model_validate(raw)

    assert lineup.formation == "4-3-3"
    assert len(lineup.startXI) == 1
    assert lineup.startXI[0].player.name == "Foo"
    assert lineup.startXI[0].player.pos == "G"
