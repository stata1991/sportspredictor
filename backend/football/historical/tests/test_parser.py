"""Unit tests for the historical fixture parser.

Uses fixed JSON samples — no real API calls.
"""

from __future__ import annotations

import pytest
import pandas as pd

from backend.football.historical.parser import parse_fixtures, COMPLETED_STATUSES


def _make_fixture(
    *,
    fixture_id: int = 1,
    league_id: int = 1,
    season: int = 2022,
    date: str = "2022-11-20T16:00:00+00:00",
    status_short: str = "FT",
    home_id: int = 10,
    home_name: str = "Team A",
    away_id: int = 20,
    away_name: str = "Team B",
    ft_home: int | None = 2,
    ft_away: int | None = 1,
    ht_home: int | None = 1,
    ht_away: int | None = 0,
    et_home: int | None = None,
    et_away: int | None = None,
    pen_home: int | None = None,
    pen_away: int | None = None,
) -> dict:
    """Build a raw fixture dict matching the API-Football response shape."""
    return {
        "fixture": {
            "id": fixture_id,
            "referee": "Ref Name",
            "timezone": "UTC",
            "date": date,
            "timestamp": 1668960000,
            "status": {"long": "Match Finished", "short": status_short, "elapsed": 90},
        },
        "league": {"id": league_id, "name": "World Cup", "season": season, "round": "Group A - 1"},
        "teams": {
            "home": {"id": home_id, "name": home_name, "logo": "", "winner": True},
            "away": {"id": away_id, "name": away_name, "logo": "", "winner": False},
        },
        "goals": {"home": ft_home, "away": ft_away},
        "score": {
            "halftime": {"home": ht_home, "away": ht_away},
            "fulltime": {"home": ft_home, "away": ft_away},
            "extratime": {"home": et_home, "away": et_away},
            "penalty": {"home": pen_home, "away": pen_away},
        },
    }


class TestParseFixtures:
    """Tests for the parse_fixtures function."""

    def test_ft_match_included_with_correct_score(self):
        """FT match is included and uses fulltime score."""
        raw = [_make_fixture(status_short="FT", ft_home=3, ft_away=1)]
        df = parse_fixtures(raw)

        assert len(df) == 1
        assert df.iloc[0]["home_goals"] == 3
        assert df.iloc[0]["away_goals"] == 1
        assert df.iloc[0]["status_short"] == "FT"

    def test_aet_match_uses_regulation_time_score(self):
        """AET match is included but uses fulltime (regulation) score.

        In API-Football, score.fulltime for AET matches contains the
        score at end of 90 minutes (or 120 in some edge cases).
        The key insight: for Dixon-Coles we want the regulation-time
        outcome, not the extra-time result.
        """
        raw = [_make_fixture(
            fixture_id=2,
            status_short="AET",
            ft_home=1,
            ft_away=1,
            et_home=2,
            et_away=1,
        )]
        df = parse_fixtures(raw)

        assert len(df) == 1
        assert df.iloc[0]["home_goals"] == 1
        assert df.iloc[0]["away_goals"] == 1
        assert df.iloc[0]["status_short"] == "AET"

    def test_pen_match_uses_regulation_time_score(self):
        """PEN match is included with regulation-time draw score.

        A PEN match was a draw after extra time; the fulltime score
        reflects the 90-minute result (a draw).  Penalty shootout
        results are NOT training signal.
        """
        raw = [_make_fixture(
            fixture_id=3,
            status_short="PEN",
            ft_home=1,
            ft_away=1,
            et_home=1,
            et_away=1,
            pen_home=4,
            pen_away=2,
        )]
        df = parse_fixtures(raw)

        assert len(df) == 1
        assert df.iloc[0]["home_goals"] == 1
        assert df.iloc[0]["away_goals"] == 1
        assert df.iloc[0]["status_short"] == "PEN"

    def test_non_completed_statuses_excluded(self):
        """Scheduled, postponed, cancelled, etc. are excluded."""
        raw = [
            _make_fixture(fixture_id=10, status_short="NS"),
            _make_fixture(fixture_id=11, status_short="PST"),
            _make_fixture(fixture_id=12, status_short="CANC"),
            _make_fixture(fixture_id=13, status_short="ABD"),
            _make_fixture(fixture_id=14, status_short="SUSP"),
            _make_fixture(fixture_id=15, status_short="INT"),
            _make_fixture(fixture_id=1, status_short="FT", ft_home=2, ft_away=0),
        ]
        df = parse_fixtures(raw)

        assert len(df) == 1
        assert df.iloc[0]["fixture_id"] == 1

    def test_null_fulltime_score_skipped(self):
        """Completed fixture with null score is skipped."""
        raw = [_make_fixture(status_short="FT", ft_home=None, ft_away=None)]
        df = parse_fixtures(raw)
        assert len(df) == 0

    def test_all_required_columns_present(self):
        """DataFrame has all required columns."""
        expected_cols = {
            "fixture_id", "league_id", "season", "kickoff_utc",
            "home_team_id", "home_team_name", "away_team_id", "away_team_name",
            "home_goals", "away_goals", "ht_home_goals", "ht_away_goals",
            "status_short",
        }
        raw = [_make_fixture()]
        df = parse_fixtures(raw)
        assert expected_cols.issubset(set(df.columns))

    def test_kickoff_utc_is_datetime(self):
        """kickoff_utc column is parsed as datetime with UTC timezone."""
        raw = [_make_fixture(date="2022-11-20T16:00:00+00:00")]
        df = parse_fixtures(raw)
        assert pd.api.types.is_datetime64_any_dtype(df["kickoff_utc"])

    def test_sorted_by_kickoff(self):
        """Fixtures are sorted chronologically."""
        raw = [
            _make_fixture(fixture_id=2, date="2022-12-01T16:00:00+00:00"),
            _make_fixture(fixture_id=1, date="2022-11-20T16:00:00+00:00"),
            _make_fixture(fixture_id=3, date="2022-12-18T16:00:00+00:00"),
        ]
        df = parse_fixtures(raw)
        assert list(df["fixture_id"]) == [1, 2, 3]

    def test_empty_input(self):
        """Empty input returns an empty DataFrame."""
        df = parse_fixtures([])
        assert len(df) == 0

    def test_mixed_statuses_in_batch(self):
        """A realistic mix of statuses is parsed correctly."""
        raw = [
            _make_fixture(fixture_id=1, status_short="FT", ft_home=2, ft_away=0),
            _make_fixture(fixture_id=2, status_short="AET", ft_home=1, ft_away=1, et_home=2, et_away=1),
            _make_fixture(fixture_id=3, status_short="PEN", ft_home=0, ft_away=0, pen_home=3, pen_away=4),
            _make_fixture(fixture_id=4, status_short="NS"),
            _make_fixture(fixture_id=5, status_short="PST"),
        ]
        df = parse_fixtures(raw)

        assert len(df) == 3
        assert set(df["fixture_id"]) == {1, 2, 3}
        # AET match: regulation-time draw
        aet_row = df[df["fixture_id"] == 2].iloc[0]
        assert aet_row["home_goals"] == 1 and aet_row["away_goals"] == 1
        # PEN match: regulation-time 0-0
        pen_row = df[df["fixture_id"] == 3].iloc[0]
        assert pen_row["home_goals"] == 0 and pen_row["away_goals"] == 0

    def test_halftime_none_preserved(self):
        """Missing halftime scores are stored as None/NaN."""
        raw = [_make_fixture(ht_home=None, ht_away=None)]
        df = parse_fixtures(raw)
        assert pd.isna(df.iloc[0]["ht_home_goals"])
        assert pd.isna(df.iloc[0]["ht_away_goals"])
