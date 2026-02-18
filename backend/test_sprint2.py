"""
Sprint 2 tests for prediction_engine_api.py

Validates:
1. Toss adjustment with chase priors (pre-match post-toss)
2. Chase prior blend in live 2nd innings
3. Innings break detection
4. Live total score range during 1st innings (projection-based)

All upstream API calls are mocked -- no network needed.
"""

from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

from backend.feature_store import SeriesFeatures, TeamForm, VenuePriors, SeriesPriors
from backend.prediction_engine_api import pre_match_predictions, live_predictions


# ---------------------------------------------------------------------------
# Helpers to build mock data
# ---------------------------------------------------------------------------

def _make_match_info(
    team1: str = "Team A",
    team2: str = "Team B",
    venue: str = "Test Ground",
    match_id: int = 101,
    status: str = "Preview",
    start_date: int = 1715299200000,
) -> dict:
    """Return a match-info dict shaped like fetch_live_data_for_series output."""
    return {
        "team1": {"teamName": team1},
        "team2": {"teamName": team2},
        "venueInfo": {"ground": venue},
        "matchId": match_id,
        "status": status,
        "startDate": start_date,
    }


def _make_features(
    team1: str = "Team A",
    team2: str = "Team B",
    venue: str | None = None,
    chase_priors: dict | None = None,
    venue_avg_runs: float = 160.0,
    venue_std_runs: float = 20.0,
) -> SeriesFeatures:
    """Build a SeriesFeatures with sensible defaults for both teams."""
    team_form = {
        team1: TeamForm(played=5, wins=3),
        team2: TeamForm(played=5, wins=2),
    }
    venue_priors: dict[str, VenuePriors] = {}
    if venue:
        venue_priors[venue] = VenuePriors(
            avg_innings_runs=venue_avg_runs,
            std_innings_runs=venue_std_runs,
            avg_innings_wkts=7.0,
            std_innings_wkts=2.0,
            pp_ratio=0.28,
            sample_size=10,
        )
    return SeriesFeatures(
        team_form=team_form,
        venue_priors=venue_priors,
        chase_priors=chase_priors or {},
        series_priors=None,
    )


# Patch targets -- these are looked up in the *prediction_engine_api* module namespace
PATCH_FETCH = "backend.prediction_engine_api.fetch_live_data_for_series"
PATCH_DETAILS = "backend.prediction_engine_api.get_match_details"
PATCH_FEATURES = "backend.prediction_engine_api.build_series_features"


# ---------------------------------------------------------------------------
# Test 1 -- Toss adjustment with chase priors (post-toss, pre-match)
# ---------------------------------------------------------------------------

@patch(PATCH_FEATURES)
@patch(PATCH_DETAILS)
@patch(PATCH_FETCH)
def test_toss_adjustment_with_chase_priors(mock_fetch, mock_details, mock_features):
    """Post-toss pre-match: toss info should trigger chase-prior-based adjustment."""

    mock_fetch.return_value = [
        _make_match_info(status="Preview", match_id=101),
    ]

    # get_match_details is called twice in pre_match_predictions:
    #   1st call: check if match is in-progress (innings check)
    #   2nd call: toss info section
    # Both should return the same post-toss, no-innings dict.
    details = {
        "toss_winner": "Team A",
        "toss_decision": "bat",
        "playing_11": {
            "Team A": ["P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8", "P9", "P10", "P11"],
            "Team B": ["P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8", "P9", "P10", "P11"],
        },
        "innings": [],
    }
    mock_details.return_value = details

    chase_priors = {"0-140": 0.4, "141-160": 0.5, "161-180": 0.6, "181+": 0.7}
    mock_features.return_value = _make_features(
        venue="Test Ground",
        chase_priors=chase_priors,
    )

    result = pre_match_predictions(series_id=9237, date="2025-05-10", match_number=0)

    assert result["prediction_stage"] == "post_toss"

    toss_adj = result["features_used"]["toss_adjustment"]
    assert toss_adj is not None
    assert toss_adj["source"] == "chase_priors"
    assert "+toss_adjusted" in result["features_used"]["winner_method"]

    # Structural checks on toss_adjustment payload
    assert "batting_first" in toss_adj
    assert "chasing_team" in toss_adj
    assert "delta" in toss_adj
    assert "overall_chase_rate" in toss_adj


# ---------------------------------------------------------------------------
# Test 2 -- Chase prior blend during 2nd-innings live chase
# ---------------------------------------------------------------------------

@patch(PATCH_FEATURES)
@patch(PATCH_DETAILS)
@patch(PATCH_FETCH)
def test_chase_prior_blend_in_live(mock_fetch, mock_details, mock_features):
    """2nd innings live chase should blend projection with historical chase prior."""

    mock_fetch.return_value = [
        _make_match_info(status="In Progress", match_id=101),
    ]

    mock_details.return_value = {
        "toss_winner": "Team B",
        "toss_decision": "field",
        "playing_11": {},
        "innings": [
            {"inningsId": 1, "batTeamName": "Team A", "score": 170, "wickets": 8, "overs": 20.0},
            {"inningsId": 2, "batTeamName": "Team B", "score": 100, "wickets": 3, "overs": 12.0},
        ],
        "powerplay": {},
        "venue": "Test Ground",
        "team1": "Team A",
        "team2": "Team B",
    }

    mock_features.return_value = _make_features(
        venue="Test Ground",
        chase_priors={"161-180": 0.55},
    )

    result = live_predictions(series_id=9237, date="2025-05-10", match_number=0)

    assert result["prediction_stage"] == "live"

    chase_prior = result["features_used"]["chase_prior_used"]
    assert chase_prior is not None
    assert chase_prior["band"] == "161-180"
    assert chase_prior["historical_rate"] == 0.55
    assert "chase_prior_blend" in result["features_used"]["winner_method"]

    # Winner probabilities must be populated
    assert result["winner"]["probabilities"] is not None
    assert len(result["winner"]["probabilities"]) == 2


# ---------------------------------------------------------------------------
# Test 3 -- Innings break detection (1st innings complete, 2nd not started)
# ---------------------------------------------------------------------------

@patch(PATCH_FEATURES)
@patch(PATCH_DETAILS)
@patch(PATCH_FETCH)
def test_innings_break_detection(mock_fetch, mock_details, mock_features):
    """When 1st innings is complete and 2nd hasn't started, stage should be innings_break."""

    mock_fetch.return_value = [
        _make_match_info(status="In Progress", match_id=101),
    ]

    mock_details.return_value = {
        "toss_winner": "Team A",
        "toss_decision": "bat",
        "playing_11": {},
        "innings": [
            {"inningsId": 1, "batTeamName": "Team A", "score": 185, "wickets": 6, "overs": 20.0},
        ],
        "powerplay": {},
        "venue": "Test Ground",
        "team1": "Team A",
        "team2": "Team B",
    }

    mock_features.return_value = _make_features(
        venue="Test Ground",
        chase_priors={"181+": 0.45},
    )

    result = live_predictions(series_id=9237, date="2025-05-10", match_number=0)

    assert result["prediction_stage"] == "innings_break"
    assert result["first_innings"]["score"] == 185
    assert result["target"] == 186
    assert result["features_used"]["chase_prior_used"]["band"] == "181+"

    # Winner must be populated
    assert result["winner"] is not None
    assert result["winner"]["team"] is not None


# ---------------------------------------------------------------------------
# Test 4 -- Live total-score range uses projection during 1st innings
# ---------------------------------------------------------------------------

@patch(PATCH_FEATURES)
@patch(PATCH_DETAILS)
@patch(PATCH_FETCH)
def test_live_total_score_range_1st_innings(mock_fetch, mock_details, mock_features):
    """During 1st innings, total_score mid should track projected_total, not static avg_runs."""

    mock_fetch.return_value = [
        _make_match_info(status="In Progress", match_id=101),
    ]

    mock_details.return_value = {
        "toss_winner": "Team A",
        "toss_decision": "bat",
        "playing_11": {},
        "innings": [
            {"inningsId": 1, "batTeamName": "Team A", "score": 90, "wickets": 2, "overs": 10.0},
        ],
        "powerplay": {},
        "venue": "Test Ground",
        "team1": "Team A",
        "team2": "Team B",
    }

    venue_avg = 165.0
    venue_std = 20.0

    mock_features.return_value = _make_features(
        venue="Test Ground",
        venue_avg_runs=venue_avg,
        venue_std_runs=venue_std,
    )

    result = live_predictions(series_id=9237, date="2025-05-10", match_number=0)

    assert result["prediction_stage"] == "live"

    projected = result["projected_total"]
    # 90 runs in 10 overs = 9.0 run-rate; 10 remaining overs -> 90 + 90 = 180
    assert projected is not None
    assert abs(projected - 180) <= 1, f"Expected projected_total ~180, got {projected}"

    # total_score mid should be close to projected_total, NOT the static venue avg (165)
    mid = result["total_score"]["mid"]
    assert abs(mid - projected) <= 2, (
        f"total_score mid ({mid}) should track projected_total ({projected}), not venue avg ({venue_avg})"
    )

    # Uncertainty shrinks: live_std = venue_std * (remaining_overs/20) = 20 * 0.5 = 10
    # So the range (high - low) should be roughly 2*10 = 20, which is narrower than
    # the pre-match range of 2*20 = 40.
    pre_match_range = 2 * max(venue_std, 12.0)
    live_range = result["total_score"]["high"] - result["total_score"]["low"]
    assert live_range < pre_match_range, (
        f"Live range ({live_range}) should be narrower than pre-match range ({pre_match_range})"
    )
