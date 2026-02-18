from __future__ import annotations

from dataclasses import dataclass
from statistics import mean, pstdev
from typing import Dict, List, Optional

from backend.cache import cache
from backend.config import FEATURE_TTL
from backend.live_data_provider import fetch_series_matches_for_id, get_match_details


@dataclass
class VenuePriors:
    avg_innings_runs: float
    std_innings_runs: float
    avg_innings_wkts: float
    std_innings_wkts: float
    pp_ratio: Optional[float]
    sample_size: int = 0


@dataclass
class SeriesPriors:
    avg_innings_runs: float
    std_innings_runs: float
    avg_innings_wkts: float
    std_innings_wkts: float
    pp_ratio: Optional[float]
    sample_size: int = 0


@dataclass
class TeamForm:
    played: int
    wins: int

    @property
    def win_rate(self) -> float:
        if self.played == 0:
            return 0.0
        return self.wins / self.played


@dataclass
class SeriesFeatures:
    team_form: Dict[str, TeamForm]
    venue_priors: Dict[str, VenuePriors]
    chase_priors: Dict[str, float]
    series_priors: Optional[SeriesPriors]


TARGET_BANDS = [
    (0, 140, "0-140"),
    (141, 160, "141-160"),
    (161, 180, "161-180"),
    (181, 9999, "181+"),
]


def _band_for_target(target: int) -> str:
    for low, high, label in TARGET_BANDS:
        if low <= target <= high:
            return label
    return "181+"


def _extract_match_scores(match) -> Optional[dict]:
    score = match.get("matchScore", {})
    team1 = match.get("matchInfo", {}).get("team1", {}).get("teamName")
    team2 = match.get("matchInfo", {}).get("team2", {}).get("teamName")
    team1_score = score.get("team1Score", {}).get("inngs1")
    team2_score = score.get("team2Score", {}).get("inngs1")
    if not team1 or not team2 or not team1_score or not team2_score:
        return None
    return {
        "team1": team1,
        "team2": team2,
        "team1_runs": team1_score.get("runs"),
        "team1_wkts": team1_score.get("wickets"),
        "team2_runs": team2_score.get("runs"),
        "team2_wkts": team2_score.get("wickets"),
    }


def build_series_features(series_id: int) -> SeriesFeatures:
    cache_key = f"ft:series:{series_id}:features:v1"
    cached = cache.get(cache_key)
    if cached:
        return cached

    matches = fetch_series_matches_for_id(series_id)
    team_form: Dict[str, TeamForm] = {}
    venue_runs: Dict[str, List[float]] = {}
    venue_wkts: Dict[str, List[float]] = {}
    venue_pp_ratio: Dict[str, List[float]] = {}
    series_runs: List[float] = []
    series_wkts: List[float] = []
    series_pp_ratios: List[float] = []
    chase_bands: Dict[str, List[int]] = {label: [] for _, _, label in TARGET_BANDS}

    for match in matches:
        info = match.get("matchInfo", {})
        status = info.get("status", "")
        if "won by" not in status.lower():
            continue
        venue = info.get("venueInfo", {}).get("ground")
        scores = _extract_match_scores(match)
        if not scores or not venue:
            continue

        team1 = scores["team1"]
        team2 = scores["team2"]
        team1_runs = scores["team1_runs"]
        team2_runs = scores["team2_runs"]
        team1_wkts = scores["team1_wkts"]
        team2_wkts = scores["team2_wkts"]

        if None in (team1_runs, team2_runs, team1_wkts, team2_wkts):
            continue

        venue_runs.setdefault(venue, []).extend([team1_runs, team2_runs])
        venue_wkts.setdefault(venue, []).extend([team1_wkts, team2_wkts])
        series_runs.extend([team1_runs, team2_runs])
        series_wkts.extend([team1_wkts, team2_wkts])

        # Winner parsing from status
        winner = team1 if status.lower().startswith(team1.lower()) else team2 if status.lower().startswith(team2.lower()) else None
        for team in (team1, team2):
            tf = team_form.get(team) or TeamForm(played=0, wins=0)
            tf.played += 1
            if winner and team.lower() == winner.lower():
                tf.wins += 1
            team_form[team] = tf

        target = int(team1_runs)
        chased = 1 if int(team2_runs) >= target + 1 else 0
        chase_bands[_band_for_target(target)].append(chased)

        # Powerplay ratio via match details (cached)
        match_id = info.get("matchId")
        if match_id:
            details = get_match_details(match_id)
            if details and details.get("powerplay"):
                pp = details.get("powerplay")
                for team, pp_stats in pp.items():
                    pp_runs = pp_stats.get("runs")
                    if team == team1:
                        total_runs = team1_runs
                    elif team == team2:
                        total_runs = team2_runs
                    else:
                        continue
                    if total_runs and pp_runs:
                        venue_pp_ratio.setdefault(venue, []).append(pp_runs / total_runs)
                        series_pp_ratios.append(pp_runs / total_runs)

    venue_priors: Dict[str, VenuePriors] = {}
    for venue, runs in venue_runs.items():
        wkts = venue_wkts.get(venue, [])
        if len(runs) < 2 or len(wkts) < 2:
            continue
        pp_list = venue_pp_ratio.get(venue)
        venue_priors[venue] = VenuePriors(
            avg_innings_runs=mean(runs),
            std_innings_runs=pstdev(runs),
            avg_innings_wkts=mean(wkts),
            std_innings_wkts=pstdev(wkts),
            pp_ratio=mean(pp_list) if pp_list else None,
            sample_size=len(runs) // 2,
        )

    chase_priors: Dict[str, float] = {}
    for band, outcomes in chase_bands.items():
        if outcomes:
            chase_priors[band] = sum(outcomes) / len(outcomes)

    series_priors = None
    if len(series_runs) >= 2 and len(series_wkts) >= 2:
        series_priors = SeriesPriors(
            avg_innings_runs=mean(series_runs),
            std_innings_runs=pstdev(series_runs),
            avg_innings_wkts=mean(series_wkts),
            std_innings_wkts=pstdev(series_wkts),
            pp_ratio=mean(series_pp_ratios) if series_pp_ratios else None,
            sample_size=len(series_runs) // 2,
        )

    features = SeriesFeatures(
        team_form=team_form,
        venue_priors=venue_priors,
        chase_priors=chase_priors,
        series_priors=series_priors,
    )
    cache.set(cache_key, features, FEATURE_TTL)
    return features
