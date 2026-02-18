from __future__ import annotations

from typing import Dict, Optional, Tuple
from datetime import datetime
import math
import logging

from backend.feature_store import build_series_features, SeriesFeatures
from backend.live_data_provider import fetch_live_data_for_series, get_match_details, UpstreamError

logger = logging.getLogger(__name__)

LEAGUE_PRIORS = {
    "avg_runs": 160.0,
    "std_runs": 25.0,
    "avg_wkts": 7.0,
    "std_wkts": 2.5,
    "pp_ratio": 0.28,
}


class MatchNotFound(Exception):
    pass


def _uncertainty_from_confidence(confidence: float) -> str:
    if confidence >= 0.7:
        return "low"
    if confidence >= 0.55:
        return "medium"
    return "high"

def _round_prob(prob: float, fallback_level: str) -> float:
    precision = 3 if fallback_level == "venue" else 2
    return round(prob, precision)

def _range_from_stats(avg: float, std: float, cap: Optional[int] = None) -> Dict[str, int]:
    low = max(0, int(round(avg - std)))
    mid = max(0, int(round(avg)))
    high = max(low, int(round(avg + std)))
    if cap is not None:
        low = min(low, cap)
        mid = min(mid, cap)
        high = min(high, cap)
    return {"low": low, "mid": mid, "high": high}


def _fallback_level_for(prior_source: str) -> str:
    if prior_source == "venue":
        return "venue"
    if prior_source == "series":
        return "series"
    return "league"


def _pick_match(series_id: int, date: str, match_number: int = 0):
    matches = fetch_live_data_for_series(date, series_id)
    if not matches or match_number >= len(matches):
        return None
    return matches[match_number]


def _resolve_priors(features: SeriesFeatures, venue: str) -> Tuple[str, float, float, float, float, float, int, str]:
    """Select venue → series → league priors and return (source, avg_runs, std_runs, avg_wkts, std_wkts, pp_ratio, sample_size, fallback_reason)."""
    venue_prior = features.venue_priors.get(venue)
    series_prior = features.series_priors
    if venue_prior:
        return (
            "venue", venue_prior.avg_innings_runs, venue_prior.std_innings_runs,
            venue_prior.avg_innings_wkts, venue_prior.std_innings_wkts,
            venue_prior.pp_ratio if venue_prior.pp_ratio else LEAGUE_PRIORS["pp_ratio"],
            venue_prior.sample_size,
            f"Venue '{venue}' has {venue_prior.sample_size} completed matches in series",
        )
    if series_prior:
        return (
            "series", series_prior.avg_innings_runs, series_prior.std_innings_runs,
            series_prior.avg_innings_wkts, series_prior.std_innings_wkts,
            series_prior.pp_ratio if series_prior.pp_ratio else LEAGUE_PRIORS["pp_ratio"],
            series_prior.sample_size,
            f"No venue data for '{venue}'; using series averages ({series_prior.sample_size} matches)",
        )
    return (
        "league", LEAGUE_PRIORS["avg_runs"], LEAGUE_PRIORS["std_runs"],
        LEAGUE_PRIORS["avg_wkts"], LEAGUE_PRIORS["std_wkts"], LEAGUE_PRIORS["pp_ratio"],
        0,
        f"No venue or series data available; using hardcoded T20 league averages",
    )


def pre_match_predictions(series_id: int, date: str, match_number: int = 0) -> Dict:
    match = _pick_match(series_id, date, match_number)
    if not match:
        raise MatchNotFound(f"No match found for date {date} and match_number {match_number}.")

    team1 = match["team1"]["teamName"]
    team2 = match["team2"]["teamName"]
    venue = match["venueInfo"]["ground"]
    status = (match.get("status") or "").lower()
    match_id = match.get("matchId")

    if any(token in status for token in ["won by", "match tied", "no result", "abandoned", "complete"]):
        return {
            "prediction_stage": "completed",
            "match": {"team1": team1, "team2": team2, "venue": venue, "date": date},
            "status": match.get("status"),
            "message": "Match already completed. Showing final status only.",
        }

    if match_id:
        details = get_match_details(match_id)
        if details and details.get("innings"):
            innings = details.get("innings", [])
            if any((inn.get("overs", 0) or 0) > 0 or (inn.get("score", 0) or 0) > 0 for inn in innings):
                return {
                    "prediction_stage": "in_progress",
                    "match": {"team1": team1, "team2": team2, "venue": venue, "date": date},
                    "status": match.get("status"),
                    "message": "Match already started. Use Live tab for current predictions.",
                }

    features = build_series_features(series_id)
    form1 = features.team_form.get(team1)
    form2 = features.team_form.get(team2)

    win_probs = {team1: 0.5, team2: 0.5}
    winner_method = "default_50_50"
    if form1 and form2 and (form1.win_rate + form2.win_rate) > 0:
        total_rate = form1.win_rate + form2.win_rate
        win_probs = {team1: form1.win_rate / total_rate, team2: form2.win_rate / total_rate}
        winner_method = "series_form_ratio"

    prior_source, avg_runs, std_runs, avg_wkts, std_wkts, pp_ratio, sample_size, fallback_reason = _resolve_priors(features, venue)

    innings_range = _range_from_stats(avg_runs, max(std_runs, 12.0))
    wickets_range = _range_from_stats(avg_wkts, max(std_wkts, 2.0), cap=10)
    total_score_range = _range_from_stats(avg_runs, max(std_runs, 12.0))
    pp_low = int(round(innings_range["low"] * pp_ratio))
    pp_mid = int(round(innings_range["mid"] * pp_ratio))
    pp_high = int(round(innings_range["high"] * pp_ratio))

    fallback_levels = [_fallback_level_for(prior_source)]
    if not (form1 and form2):
        fallback_levels.append("league")
        fallback_reason += "; team form unavailable for one or both teams"

    fallback_level = "league" if "league" in fallback_levels else "series" if "series" in fallback_levels else "venue"
    confidence = 0.7 if fallback_level == "venue" else 0.58 if fallback_level == "series" else 0.48
    data_quality = "good" if fallback_level == "venue" else "degraded"

    prediction_stage = "pre_toss"
    if match_id:
        details = get_match_details(match_id)
        if details and (details.get("toss_winner") or details.get("toss_decision") or details.get("playing_11")):
            prediction_stage = "post_toss"
            confidence = min(0.8, confidence + 0.05)

    winner_team = max(win_probs, key=win_probs.get)

    return {
        "prediction_stage": prediction_stage,
        "data_quality": data_quality,
        "fallback_level": fallback_level,
        "fallback_reason": fallback_reason,
        "sample_size": sample_size,
        "confidence": round(confidence, 2),
        "uncertainty": _uncertainty_from_confidence(confidence),
        "match": {
            "team1": team1,
            "team2": team2,
            "venue": venue,
            "date": date,
        },
        "features_used": {
            "prior_source": prior_source,
            "avg_runs": round(avg_runs, 2),
            "std_runs": round(std_runs, 2),
            "avg_wkts": round(avg_wkts, 2),
            "std_wkts": round(std_wkts, 2),
            "pp_ratio": round(pp_ratio, 3),
            "winner_method": winner_method,
            "team1_form": {"played": form1.played, "wins": form1.wins, "win_rate": round(form1.win_rate, 3)} if form1 else None,
            "team2_form": {"played": form2.played, "wins": form2.wins, "win_rate": round(form2.win_rate, 3)} if form2 else None,
        },
        "winner": {
            "team": winner_team,
            "probability": _round_prob(win_probs[winner_team], fallback_level),
            "probabilities": {
                team1: _round_prob(win_probs[team1], fallback_level),
                team2: _round_prob(win_probs[team2], fallback_level),
            },
        },
        "total_score": total_score_range,
        "wickets": wickets_range,
        "powerplay": {"low": min(pp_low, pp_high), "mid": pp_mid, "high": max(pp_low, pp_high)},
    }


def live_predictions(series_id: int, date: str, match_number: int = 0) -> Dict:
    match = _pick_match(series_id, date, match_number)
    if not match:
        raise MatchNotFound(f"No match found for date {date} and match_number {match_number}.")

    match_id = match.get("matchId")
    if not match_id:
        raise MatchNotFound("Match ID not available.")

    details = get_match_details(match_id)
    if not details:
        raise MatchNotFound("Live match data unavailable.")

    innings = details.get("innings", [])
    if not innings:
        pre_match = pre_match_predictions(series_id=series_id, date=date, match_number=match_number)
        pre_match["message"] = "Match has not started yet. Showing pre-match prediction."
        return pre_match

    current_innings = max(innings, key=lambda x: x.get("inningsId", 0))
    batting_team = current_innings.get("batTeamName")
    runs = current_innings.get("score", 0)
    wickets = current_innings.get("wickets", 0)
    overs = float(current_innings.get("overs", 0.0))

    first_innings = min(innings, key=lambda x: x.get("inningsId", 0))
    first_team = first_innings.get("batTeamName")
    target = first_innings.get("score", 0) + 1 if batting_team and batting_team != first_team else None

    current_rr = (runs / overs) if overs > 0 else 0
    remaining_overs = max(0.0, 20.0 - overs)
    projected_final = int(round(runs + current_rr * remaining_overs)) if overs > 0 else None

    chase = None
    chase_outcome = None
    if target:
        overs_int = int(overs)
        balls_in_over = int(round((overs - overs_int) * 10))
        balls_elapsed = overs_int * 6 + balls_in_over
        balls_remaining = max(0, 120 - balls_elapsed)
        required_rr = (target - runs) / (balls_remaining / 6) if balls_remaining > 0 else None
        chase = {
            "target": int(target),
            "required_run_rate": round(required_rr, 2) if required_rr is not None else None,
        }
        if projected_final is not None:
            if projected_final >= target:
                balls_needed = 0
                if current_rr > 0 and target > runs:
                    balls_needed = int(math.ceil((target - runs) / current_rr * 6))
                finish_balls = balls_elapsed + balls_needed
                chase_outcome = {
                    "can_chase": True,
                    "finish_over": int(finish_balls // 6),
                    "finish_ball": int(finish_balls % 6),
                    "short_by": None,
                }
            else:
                chase_outcome = {
                    "can_chase": False,
                    "finish_over": None,
                    "finish_ball": None,
                    "short_by": int(math.ceil(target - projected_final)),
                }

    features = build_series_features(series_id)
    venue = match["venueInfo"]["ground"]
    team1 = match["team1"]["teamName"]
    team2 = match["team2"]["teamName"]

    prior_source, avg_runs, std_runs, avg_wkts, std_wkts, pp_ratio, sample_size, fallback_reason = _resolve_priors(features, venue)

    innings_range = _range_from_stats(avg_runs, max(std_runs, 12.0))
    wickets_range = _range_from_stats(avg_wkts, max(std_wkts, 2.0), cap=10)
    pp_low = int(round(innings_range["low"] * pp_ratio))
    pp_mid = int(round(innings_range["mid"] * pp_ratio))
    pp_high = int(round(innings_range["high"] * pp_ratio))
    total_score_range = _range_from_stats(avg_runs, max(std_runs, 12.0))

    winner = None
    win_probs = None
    winner_method = "chase_projection"
    if chase_outcome:
        winner = batting_team if chase_outcome.get("can_chase") else (team2 if batting_team == team1 else team1)
    else:
        form1 = features.team_form.get(team1)
        form2 = features.team_form.get(team2)
        if not form1 or not form2:
            return {"error": "Insufficient data for winner prediction."}
        total_rate = form1.win_rate + form2.win_rate
        if total_rate == 0:
            win_probs = {team1: 0.5, team2: 0.5}
            winner_method = "default_50_50"
        else:
            win_probs = {team1: form1.win_rate / total_rate, team2: form2.win_rate / total_rate}
            winner_method = "series_form_ratio"
        winner = max(win_probs, key=win_probs.get)

    form1 = features.team_form.get(team1)
    form2 = features.team_form.get(team2)

    fallback_levels = [_fallback_level_for(prior_source)]
    if not (form1 and form2):
        fallback_levels.append("league")
        fallback_reason += "; team form unavailable for one or both teams"
    fallback_level = "league" if "league" in fallback_levels else "series" if "series" in fallback_levels else "venue"
    confidence = 0.72 if fallback_level == "venue" else 0.6 if fallback_level == "series" else 0.48
    data_quality = "good" if fallback_level == "venue" else "degraded"

    chase_payload = None
    if chase_outcome:
        chase_payload = {
            "will_reach": bool(chase_outcome.get("can_chase")),
            "finish_at": (
                f"{chase_outcome.get('finish_over')}.{chase_outcome.get('finish_ball')}"
                if chase_outcome.get("can_chase")
                else None
            ),
            "short_by": chase_outcome.get("short_by") if not chase_outcome.get("can_chase") else None,
            "target": chase.get("target") if chase else None,
            "required_run_rate": chase.get("required_run_rate") if chase else None,
        }

    return {
        "prediction_stage": "live",
        "data_quality": data_quality,
        "fallback_level": fallback_level,
        "fallback_reason": fallback_reason,
        "sample_size": sample_size,
        "confidence": round(confidence, 2),
        "uncertainty": _uncertainty_from_confidence(confidence),
        "match": {
            "team1": team1,
            "team2": team2,
            "venue": venue,
            "date": date,
        },
        "features_used": {
            "prior_source": prior_source,
            "avg_runs": round(avg_runs, 2),
            "std_runs": round(std_runs, 2),
            "avg_wkts": round(avg_wkts, 2),
            "std_wkts": round(std_wkts, 2),
            "pp_ratio": round(pp_ratio, 3),
            "winner_method": winner_method,
            "team1_form": {"played": form1.played, "wins": form1.wins, "win_rate": round(form1.win_rate, 3)} if form1 else None,
            "team2_form": {"played": form2.played, "wins": form2.wins, "win_rate": round(form2.win_rate, 3)} if form2 else None,
        },
        "winner": {
            "team": winner,
            "probability": _round_prob(win_probs[winner], fallback_level) if win_probs and winner else None,
            "probabilities": {
                team1: _round_prob(win_probs[team1], fallback_level),
                team2: _round_prob(win_probs[team2], fallback_level),
            } if win_probs else None,
        },
        "live": {
            "batting_team": batting_team,
            "runs": runs,
            "wickets": wickets,
            "overs": overs,
            "current_run_rate": round(current_rr, 2),
        },
        "projected_total": projected_final,
        "total_score": total_score_range,
        "chase": chase_payload,
        "wickets": wickets_range,
        "powerplay": {"low": min(pp_low, pp_high), "mid": pp_mid, "high": max(pp_low, pp_high)},
    }
