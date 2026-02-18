from __future__ import annotations

from typing import Dict, Optional, Tuple
from datetime import datetime
import math
import logging

from backend.feature_store import build_series_features, SeriesFeatures, _band_for_target
from backend.live_data_provider import fetch_live_data_for_series, get_match_details, UpstreamError

logger = logging.getLogger(__name__)

LEAGUE_PRIORS = {
    "avg_runs": 160.0,
    "std_runs": 25.0,
    "avg_wkts": 7.0,
    "std_wkts": 2.5,
    "pp_ratio": 0.28,
}


DEATH_RATIO_DEFAULT = 0.27


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


def _calibrated_confidence(
    fallback_level: str, sample_size: int, overs: float = 0.0, is_live: bool = False,
) -> Tuple[float, Dict]:
    """Compute confidence from sample size instead of hardcoded tiers."""
    base = 0.48
    sample_bonus = 0.10 * min(1.0, sample_size / 20.0) if fallback_level in ("series", "venue") else 0.0
    venue_bonus = 0.05 if fallback_level == "venue" else 0.0
    live_bonus = (overs / 20.0) * 0.15 if is_live else 0.0

    raw = base + sample_bonus + venue_bonus + live_bonus
    capped = min(0.92, round(raw, 4))

    components = {
        "base": base,
        "sample_bonus": round(sample_bonus, 4),
        "venue_bonus": venue_bonus,
        "live_bonus": round(live_bonus, 4),
        "raw": round(raw, 4),
        "capped": round(capped, 2),
    }
    return capped, components


def _powerplay_model(
    avg_runs: float, std_runs: float, pp_ratio: float,
    overs: float = 0.0, runs: int = 0, is_live: bool = False,
) -> Tuple[Dict[str, int], Dict]:
    """Independent powerplay projection.

    Pre-match / post-PP: prior-based range from pp_ratio.
    Live in PP (overs < 6): actual runs + remaining PP overs at team_pp_rpo.
    """
    team_pp_rpo = pp_ratio * avg_runs / 6.0
    pp_std = max(std_runs, 12.0) * pp_ratio

    if is_live and overs < 6.0 and overs > 0:
        remaining_pp = max(0.0, 6.0 - overs)
        pp_mid = int(round(runs + team_pp_rpo * remaining_pp))
        shrink = remaining_pp / 6.0
        pp_low = max(runs, int(round(pp_mid - pp_std * shrink)))
        pp_high = int(round(pp_mid + pp_std * shrink))
        source = "live_projection"
    else:
        pp_mid = int(round(avg_runs * pp_ratio))
        pp_low = max(0, int(round(pp_mid - pp_std)))
        pp_high = int(round(pp_mid + pp_std))
        source = "prior"

    pp_range = {"low": min(pp_low, pp_high), "mid": pp_mid, "high": max(pp_low, pp_high)}
    pp_model_info = {
        "source": source,
        "team_pp_rpo": round(team_pp_rpo, 2),
        "pp_ratio_used": round(pp_ratio, 3),
    }
    return pp_range, pp_model_info


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


def _phase_projected_total(
    runs: int, overs: float, avg_runs: float, pp_ratio: float,
) -> Tuple[Optional[int], Optional[Dict]]:
    """Phase-aware projected total for 1st innings.

    Splits the innings into three phases with distinct RPO defaults derived
    from venue/series priors, then projects remaining runs per phase.
    """
    if overs <= 0:
        return None, None

    death_ratio = DEATH_RATIO_DEFAULT
    middle_ratio = max(0.0, 1.0 - pp_ratio - death_ratio)

    pp_rpo = (avg_runs * pp_ratio) / 6.0
    middle_rpo = (avg_runs * middle_ratio) / 9.0
    death_rpo = (avg_runs * death_ratio) / 5.0

    if overs <= 6.0:
        current_phase = "powerplay"
    elif overs <= 15.0:
        current_phase = "middle"
    else:
        current_phase = "death"

    projected = float(runs)

    if current_phase == "powerplay":
        remaining_pp = max(0.0, 6.0 - overs)
        projected += pp_rpo * remaining_pp
        projected += middle_rpo * 9.0
        projected += death_rpo * 5.0
    elif current_phase == "middle":
        remaining_mid = max(0.0, 15.0 - overs)
        projected += middle_rpo * remaining_mid
        projected += death_rpo * 5.0
    else:
        remaining_death = max(0.0, 20.0 - overs)
        projected += death_rpo * remaining_death

    phase_model = {
        "current_phase": current_phase,
        "pp_rpo": round(pp_rpo, 2),
        "middle_rpo": round(middle_rpo, 2),
        "death_rpo": round(death_rpo, 2),
        "projected_total": int(round(projected)),
    }

    return int(round(projected)), phase_model


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
    powerplay_range, pp_model = _powerplay_model(avg_runs, std_runs, pp_ratio)

    fallback_levels = [_fallback_level_for(prior_source)]
    if not (form1 and form2):
        fallback_levels.append("league")
        fallback_reason += "; team form unavailable for one or both teams"

    fallback_level = "league" if "league" in fallback_levels else "series" if "series" in fallback_levels else "venue"
    confidence, confidence_components = _calibrated_confidence(fallback_level, sample_size)
    data_quality = "good" if fallback_level == "venue" else "degraded"

    prediction_stage = "pre_toss"
    toss_adjustment = None
    if match_id:
        details = get_match_details(match_id)
        if details and (details.get("toss_winner") or details.get("toss_decision") or details.get("playing_11")):
            prediction_stage = "post_toss"
            confidence = min(0.92, confidence + 0.05)
            confidence_components["toss_bonus"] = 0.05
            confidence_components["capped"] = round(confidence, 2)

            # --- Toss-based win probability adjustment ---
            toss_winner = details.get("toss_winner")
            toss_decision = (details.get("toss_decision") or "").lower()
            if toss_winner and toss_decision:
                if toss_decision in ("bat", "batting"):
                    batting_first = toss_winner
                    chasing_team = team2 if toss_winner == team1 else team1
                else:  # "field", "bowl", "bowling"
                    chasing_team = toss_winner
                    batting_first = team2 if toss_winner == team1 else team1

                chase_priors = features.chase_priors
                if chase_priors:
                    overall_chase_rate = sum(chase_priors.values()) / len(chase_priors)
                    toss_delta = overall_chase_rate - 0.5
                    toss_adjustment = {
                        "source": "chase_priors",
                        "overall_chase_rate": round(overall_chase_rate, 3),
                        "delta": round(toss_delta, 3),
                        "toss_winner": toss_winner,
                        "toss_decision": toss_decision,
                        "batting_first": batting_first,
                        "chasing_team": chasing_team,
                    }
                else:
                    toss_delta = 0.05
                    toss_adjustment = {
                        "source": "flat_default",
                        "overall_chase_rate": 0.55,
                        "delta": 0.05,
                        "toss_winner": toss_winner,
                        "toss_decision": toss_decision,
                        "batting_first": batting_first,
                        "chasing_team": chasing_team,
                    }

                win_probs[chasing_team] += toss_delta
                win_probs[batting_first] -= toss_delta
                for t in (team1, team2):
                    win_probs[t] = max(0.05, min(0.95, win_probs[t]))
                total_prob = win_probs[team1] + win_probs[team2]
                win_probs = {t: p / total_prob for t, p in win_probs.items()}
                winner_method += "+toss_adjusted"
                logger.info("Toss adjustment applied: source=%s delta=%.3f chasing=%s", toss_adjustment["source"], toss_delta, chasing_team)

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
            "toss_adjustment": toss_adjustment,
            "confidence_components": confidence_components,
            "pp_model": pp_model,
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
        "powerplay": powerplay_range,
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

    # --- Detect innings break ---
    first_inn_overs = float(first_innings.get("overs", 0.0))
    first_inn_wkts = first_innings.get("wickets", 0) or 0
    is_innings_break = False
    if len(innings) == 1 and (first_inn_overs >= 20.0 or first_inn_wkts >= 10):
        is_innings_break = True
    elif len(innings) >= 2:
        second_overs = float(current_innings.get("overs", 0.0))
        second_score = current_innings.get("score", 0) or 0
        if second_overs == 0 and second_score == 0 and (first_inn_overs >= 20.0 or first_inn_wkts >= 10):
            is_innings_break = True

    if is_innings_break:
        first_innings_score = first_innings.get("score", 0) or 0
        innings_break_target = first_innings_score + 1
        team1 = match["team1"]["teamName"]
        team2 = match["team2"]["teamName"]
        venue = match["venueInfo"]["ground"]
        chasing_team = team2 if first_team == team1 else team1

        features = build_series_features(series_id)
        band = _band_for_target(innings_break_target)
        band_rate = features.chase_priors.get(band)

        if band_rate is not None:
            chase_win_prob = band_rate
            chase_prior_source = "chase_priors"
        else:
            chase_win_prob = 0.55
            chase_prior_source = "flat_default"

        win_probs = {chasing_team: chase_win_prob, first_team: 1.0 - chase_win_prob}
        for t in (team1, team2):
            win_probs[t] = max(0.05, min(0.95, win_probs[t]))
        total_prob = win_probs[team1] + win_probs[team2]
        win_probs = {t: p / total_prob for t, p in win_probs.items()}
        winner_team = max(win_probs, key=win_probs.get)

        prior_source, avg_runs, std_runs, avg_wkts, std_wkts, pp_ratio, sample_size, fallback_reason = _resolve_priors(features, venue)
        fallback_level = _fallback_level_for(prior_source)
        confidence, confidence_components = _calibrated_confidence(fallback_level, sample_size, overs=20.0, is_live=True)
        form1 = features.team_form.get(team1)
        form2 = features.team_form.get(team2)

        logger.info("Innings break detected: %s scored %d, target=%d, band=%s, rate=%s",
                     first_team, first_innings_score, innings_break_target, band, band_rate)

        return {
            "prediction_stage": "innings_break",
            "data_quality": "good" if fallback_level == "venue" else "degraded",
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
            "first_innings": {
                "batting_team": first_team,
                "score": first_innings_score,
                "wickets": first_inn_wkts,
                "overs": first_inn_overs,
            },
            "target": innings_break_target,
            "features_used": {
                "prior_source": prior_source,
                "avg_runs": round(avg_runs, 2),
                "std_runs": round(std_runs, 2),
                "winner_method": "pre_chase_prior",
                "chase_prior_used": {
                    "band": band,
                    "historical_rate": round(band_rate, 3) if band_rate is not None else None,
                    "source": chase_prior_source,
                },
                "confidence_components": confidence_components,
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
        }

    features = build_series_features(series_id)
    venue = match["venueInfo"]["ground"]
    team1 = match["team1"]["teamName"]
    team2 = match["team2"]["teamName"]

    prior_source, avg_runs, std_runs, avg_wkts, std_wkts, pp_ratio, sample_size, fallback_reason = _resolve_priors(features, venue)

    current_rr = (runs / overs) if overs > 0 else 0
    remaining_overs = max(0.0, 20.0 - overs)

    # --- Phase-aware projection for 1st innings; simple for chase ---
    phase_model = None
    if target is None and overs > 0:
        projected_final, phase_model = _phase_projected_total(runs, overs, avg_runs, pp_ratio)
    else:
        projected_final = int(round(runs + current_rr * remaining_overs)) if overs > 0 else None

    # --- Wickets-in-hand pressure for chase ---
    wickets_pressure = None
    if target and projected_final is not None:
        wickets_in_hand = 10 - wickets
        if wickets_in_hand >= 8:
            wkt_multiplier = 1.0
        elif wickets_in_hand >= 6:
            wkt_multiplier = 0.92
        elif wickets_in_hand >= 4:
            wkt_multiplier = 0.80
        elif wickets_in_hand >= 2:
            wkt_multiplier = 0.65
        else:
            wkt_multiplier = 0.45

        rrr_pressure = 1.0
        if current_rr > 0:
            required_rr_raw = (target - runs) / (remaining_overs if remaining_overs > 0 else 0.1)
            if required_rr_raw / current_rr > 1.5:
                rrr_pressure = 0.85

        combined_multiplier = wkt_multiplier * rrr_pressure
        adjusted_projection = int(round(projected_final * combined_multiplier))

        wickets_pressure = {
            "wickets_in_hand": wickets_in_hand,
            "wkt_multiplier": wkt_multiplier,
            "rrr_crr_ratio": round(required_rr_raw / current_rr, 2) if current_rr > 0 else None,
            "rrr_pressure": rrr_pressure,
            "combined_multiplier": round(combined_multiplier, 3),
            "raw_projection": projected_final,
            "adjusted_projection": adjusted_projection,
        }
        projected_final = adjusted_projection
        logger.info("Wickets pressure: wih=%d mult=%.3f rrr_p=%.2f raw=%d adj=%d",
                     wickets_in_hand, wkt_multiplier, rrr_pressure, wickets_pressure["raw_projection"], adjusted_projection)

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

    innings_range = _range_from_stats(avg_runs, max(std_runs, 12.0))
    wickets_range = _range_from_stats(avg_wkts, max(std_wkts, 2.0), cap=10)
    powerplay_range, pp_model = _powerplay_model(avg_runs, std_runs, pp_ratio, overs=overs, runs=runs, is_live=True)
    # --- Live-adjusted total_score_range ---
    if target:
        # 2nd innings: first innings total is known — no uncertainty
        first_innings_total = int(target) - 1
        total_score_range = {"low": first_innings_total, "mid": first_innings_total, "high": first_innings_total}
    elif projected_final is not None and remaining_overs < 20.0:
        # 1st innings in progress: use projection with shrinking uncertainty
        live_std = max(std_runs, 12.0) * (remaining_overs / 20.0)
        total_score_range = _range_from_stats(float(projected_final), live_std)
    else:
        # No live data yet — fall back to prior-based range
        total_score_range = _range_from_stats(avg_runs, max(std_runs, 12.0))

    winner = None
    win_probs = None
    chase_prior_used = None
    winner_method = "chase_projection"
    if chase_outcome:
        bowling_team = team2 if batting_team == team1 else team1
        linear_signal = 1.0 if chase_outcome.get("can_chase") else 0.0

        band = _band_for_target(int(target))
        band_rate = features.chase_priors.get(band)

        if band_rate is not None:
            chase_win_prob = 0.6 * linear_signal + 0.4 * band_rate
            winner_method = "chase_projection+chase_prior_blend"
            chase_prior_used = {
                "band": band,
                "historical_rate": round(band_rate, 3),
                "linear_signal": linear_signal,
                "blend": "0.6*projection+0.4*historical",
                "blended_chase_prob": round(chase_win_prob, 3),
            }
        else:
            chase_win_prob = linear_signal
            chase_prior_used = {
                "band": band,
                "historical_rate": None,
                "linear_signal": linear_signal,
                "blend": None,
                "blended_chase_prob": chase_win_prob,
            }

        win_probs = {batting_team: chase_win_prob, bowling_team: 1.0 - chase_win_prob}
        for t in (team1, team2):
            win_probs[t] = max(0.05, min(0.95, win_probs[t]))
        total_prob = win_probs[team1] + win_probs[team2]
        win_probs = {t: p / total_prob for t, p in win_probs.items()}
        winner = max(win_probs, key=win_probs.get)
        logger.info("Chase blend: band=%s rate=%s linear=%.1f blended=%.3f", band, band_rate, linear_signal, chase_win_prob)
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
    confidence, confidence_components = _calibrated_confidence(fallback_level, sample_size, overs=overs, is_live=True)
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
            "chase_prior_used": chase_prior_used,
            "phase_model": phase_model,
            "wickets_pressure": wickets_pressure,
            "confidence_components": confidence_components,
            "pp_model": pp_model,
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
        "powerplay": powerplay_range,
    }
