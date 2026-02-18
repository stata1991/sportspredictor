import os
import requests
import threading
import time as _time_mod
from datetime import datetime
from dotenv import load_dotenv
import logging
from backend.cache import cache
from backend.config import (
    SERIES_TTL, SERIES_SCHEDULE_TTL, MATCH_INFO_TTL, COMPLETED_MATCH_TTL,
    OVERS_TTL, SCORECARD_TTL,
    MATCH_LIST_TODAY_TTL, MATCH_LIST_PAST_TTL, MATCH_LIST_FUTURE_TTL,
)

logger = logging.getLogger(__name__)

# ── Per-request stats (thread-local) ──────────────────────────
_request_stats = threading.local()


def _inc_stat(name: str, amount: int = 1) -> None:
    setattr(_request_stats, name, getattr(_request_stats, name, 0) + amount)


def reset_request_stats() -> None:
    _request_stats.cache_hits = 0
    _request_stats.cache_misses = 0
    _request_stats.upstream_calls = 0
    _request_stats.upstream_latency_ms = 0
    _request_stats.start_time = _time_mod.monotonic()


def get_request_stats() -> dict:
    elapsed = int((_time_mod.monotonic() - getattr(_request_stats, 'start_time', _time_mod.monotonic())) * 1000)
    return {
        "cache_hits": getattr(_request_stats, 'cache_hits', 0),
        "cache_misses": getattr(_request_stats, 'cache_misses', 0),
        "upstream_calls": getattr(_request_stats, 'upstream_calls', 0),
        "upstream_latency_ms": getattr(_request_stats, 'upstream_latency_ms', 0),
        "total_latency_ms": elapsed,
    }


class UpstreamError(Exception):
    def __init__(self, status_code: int, message: str = "Upstream API unavailable"):
        super().__init__(message)
        self.status_code = status_code


def _cached_get_json(url: str, headers: dict, cache_key: str, ttl: int):
    def loader():
        _inc_stat('upstream_calls')
        t0 = _time_mod.monotonic()
        response = requests.get(url, headers=headers)
        latency = int((_time_mod.monotonic() - t0) * 1000)
        _inc_stat('upstream_latency_ms', latency)
        logger.info("Upstream call: %s latency=%dms status=%d", cache_key, latency, response.status_code)
        if response.status_code != 200:
            return {"_error": response.status_code, "_body": response.text}
        return response.json()

    lock = cache.with_singleflight_lock(cache_key)
    with lock:
        cached = cache.get(cache_key)
        if cached is not None:
            _inc_stat('cache_hits')
            return cached
        _inc_stat('cache_misses')
        data = loader()
        if not (isinstance(data, dict) and data.get("_error")):
            cache.set(cache_key, data, ttl)
        return data


def _stale_cached_get_json(url: str, headers: dict, cache_key: str, ttl: int, stale_ttl: int):
    """Fetch with stale-while-revalidate semantics for rarely-changing data like series info."""
    was_miss = False

    def loader():
        nonlocal was_miss
        was_miss = True
        _inc_stat('upstream_calls')
        t0 = _time_mod.monotonic()
        response = requests.get(url, headers=headers)
        latency = int((_time_mod.monotonic() - t0) * 1000)
        _inc_stat('upstream_latency_ms', latency)
        logger.info("Upstream call (stale): %s latency=%dms status=%d", cache_key, latency, response.status_code)
        if response.status_code != 200:
            raise UpstreamError(response.status_code, response.text)
        return response.json()

    result = cache.stale_while_revalidate(cache_key, ttl, stale_ttl, loader)
    _inc_stat('cache_hits' if not was_miss else 'cache_misses')
    return result


ENV_PATH = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(ENV_PATH)

BASE_URL = "https://Cricbuzz-Official-Cricket-API.proxy-production.allthingsdev.co"
API_HEADERS_BASE = {
    "x-apihub-key": os.getenv("CRICKETDATA_API_KEY"),
    "x-apihub-host": "Cricbuzz-Official-Cricket-API.allthingsdev.co",
}
SERIES_ENDPOINT = "661c6b89-b558-41fa-9553-d0aca64fcb6f"
MATCH_INFO_ENDPOINT = "ac951751-d311-4d23-8f18-353e75432353"
SCORECARD_ENDPOINT = os.getenv("CRICBUZZ_SCORECARD_ENDPOINT")
if API_HEADERS_BASE["x-apihub-key"]:
    logger.info("CRICKETDATA_API_KEY loaded (len=%s)", len(API_HEADERS_BASE["x-apihub-key"]))
else:
    logger.warning("CRICKETDATA_API_KEY is not set")


def _headers_with_endpoint(endpoint_id: str):
    headers = dict(API_HEADERS_BASE)
    headers["x-apihub-endpoint"] = endpoint_id
    return headers

IPL_TEAMS = [
    "Chennai Super Kings", "Mumbai Indians", "Rajasthan Royals",
    "Sunrisers Hyderabad", "Kolkata Knight Riders", "Gujarat Titans",
    "Lucknow Super Giants", "Royal Challengers Bengaluru", "Delhi Capitals",
    "Punjab Kings"
]

SERIES_ID = 9237

T20WC_SERIES_ID = int(os.getenv('T20WC_SERIES_ID', '0') or 0)



def fetch_series_matches_for_id(series_id: int):
    url = f"{BASE_URL}/series/{series_id}"
    cache_key = f"cb:series:{series_id}:info:v1"
    data = _stale_cached_get_json(url, _headers_with_endpoint(SERIES_ENDPOINT), cache_key, SERIES_SCHEDULE_TTL, stale_ttl=3600)

    matches = []
    for day in data.get("matchDetails", []):
        for match in day["matchDetailsMap"]["match"]:
            matches.append(match)

    return matches


def get_match_by_date_for_series(date_str: str, series_id: int):
    date_requested = datetime.strptime(date_str, "%Y-%m-%d").strftime("%a, %d %b %Y")
    matches = fetch_series_matches_for_id(series_id)

    for match in matches:
        info = match.get("matchInfo", match)
        match_date = datetime.utcfromtimestamp(int(info["startDate"]) / 1000).strftime("%a, %d %b %Y")
        if match_date == date_requested and info["matchFormat"] == "T20":
            return {
                "match_id": info["matchId"],
                "team1": info["team1"]["teamName"],
                "team2": info["team2"]["teamName"],
                "venue": info["venueInfo"]["ground"],
                "status": info["status"],
                "date": match_date
            }

    logger.info("No match found for this date")
    return None


def _match_list_ttl(date_str: str) -> int:
    """Return TTL based on date volatility: past→24h, today→1h, future→30m."""
    today = datetime.utcnow().strftime("%Y-%m-%d")
    if date_str < today:
        return MATCH_LIST_PAST_TTL
    if date_str == today:
        return MATCH_LIST_TODAY_TTL
    return MATCH_LIST_FUTURE_TTL


def fetch_live_data_for_series(date_str: str, series_id: int, teams_filter=None):
    # Check match-list cache first (keyed by series+date)
    ml_cache_key = f"cb:matches:{series_id}:{date_str}:v1"
    if not teams_filter:
        cached_ml = cache.get(ml_cache_key)
        if cached_ml is not None:
            _inc_stat('cache_hits')
            logger.info("Match list cache hit for %s %s (%d matches)", series_id, date_str, len(cached_ml))
            return cached_ml

    url = f"{BASE_URL}/series/{series_id}"
    cache_key = f"cb:series:{series_id}:info:v1"
    data = _stale_cached_get_json(url, _headers_with_endpoint(SERIES_ENDPOINT), cache_key, SERIES_SCHEDULE_TTL, stale_ttl=3600)

    formatted_date = datetime.strptime(date_str, "%Y-%m-%d").strftime('%a, %d %b %Y')
    logger.info("Formatted date for match key: %s", formatted_date)
    match_details_days = data.get("matchDetails", [])
    matches_today = []

    for day in match_details_days:
        match_day = day.get("matchDetailsMap", {})
        key = match_day.get("key")
        if key == formatted_date:
            logger.info("Found match_day for %s", formatted_date)
            for match in match_day.get("match", []):
                match_info = match["matchInfo"]
                if match_info["matchFormat"] != "T20":
                    continue
                if teams_filter:
                    if (match_info["team1"]["teamName"] not in teams_filter and
                            match_info["team2"]["teamName"] not in teams_filter):
                        continue
                matches_today.append(match_info)

    logger.info("Found %d T20 matches for %s", len(matches_today), date_str)

    # Cache filtered result (skip when teams_filter is used — custom filter)
    if not teams_filter:
        ttl = _match_list_ttl(date_str)
        cache.set(ml_cache_key, matches_today, ttl)
        logger.info("Cached match list for %s %s ttl=%ds", series_id, date_str, ttl)

    return matches_today


def get_todays_matches_for_series(date_str: str, series_id: int):
    return fetch_live_data_for_series(date_str, series_id)


def get_match_context_by_number_for_series(date_str: str, match_number: int, series_id: int):
    matches = fetch_live_data_for_series(date_str, series_id)

    if match_number >= len(matches):
        raise IndexError(f"Only {len(matches)} matches found for {date_str}. match_number={match_number} is invalid.")

    match = matches[match_number]
    match_id = match["matchId"]

    match_details = get_match_details(match_id)
    if not match_details:
        raise ValueError(f"Could not load details for match_id: {match_id}")

    return {
        "match_id": match_id,
        "team1": match["team1"]["teamName"],
        "team2": match["team2"]["teamName"],
        "venue": match["venueInfo"]["ground"],
        "status": match.get("status", "Preview"),
        "date": datetime.utcfromtimestamp(match["startDate"] / 1000).strftime("%a, %d %b %Y"),
        "playing_11": match_details.get("playing_11", {}),
        "squads": match_details.get("squads", {}),
        "toss_winner": match_details.get("toss_winner", ""),
        "toss_decision": match_details.get("toss_decision", ""),
        "innings": match_details.get("innings", []),
        "powerplay": match_details.get("powerplay", {})
    }


def get_first_innings_score_for_series(date: str, series_id: int) -> int:
    match_info = get_match_by_date_for_series(date, series_id)
    if not match_info:
        logger.warning("No match info for date %s", date)
        return 0

    match_id = match_info.get("match_id")
    match_details = get_match_details(match_id)
    if not match_details:
        logger.warning("No match details for match_id %s", match_id)
        return 0

    innings = match_details.get("innings", [])
    if not innings:
        logger.warning("No innings data found for match %s", match_id)
        return 0

    first_innings = min(innings, key=lambda x: x.get("inningsId", 1))
    return first_innings.get("score", 0)


def fetch_series_matches():
    url = f"{BASE_URL}/series/{SERIES_ID}"
    cache_key = f"cb:series:{SERIES_ID}:info:v1"
    data = _stale_cached_get_json(url, _headers_with_endpoint(SERIES_ENDPOINT), cache_key, SERIES_SCHEDULE_TTL, stale_ttl=3600)

    matches = []
    for day in data.get("matchDetails", []):
        for match in day["matchDetailsMap"]["match"]:
            matches.append(match)

    return matches


def get_todays_match():
    today_str = datetime.utcnow().strftime('%a, %d %b %Y')
    url = f"{BASE_URL}/series/{SERIES_ID}"
    cache_key = f"cb:series:{SERIES_ID}:info:v1"
    data = _stale_cached_get_json(url, _headers_with_endpoint(SERIES_ENDPOINT), cache_key, SERIES_SCHEDULE_TTL, stale_ttl=3600)

    match_maps = data.get("matchDetailsMap", data.get("matchDetails", []))

    for match_day in match_maps:
        day_map = match_day.get("matchDetailsMap", match_day)
        key = day_map.get("key", match_day.get("key"))
        if key == today_str:
            for match in day_map.get("match", []):
                match_info = match.get("matchInfo", match)
                if (match_info.get("matchFormat") == "T20" and
                    (match_info["team1"]["teamName"] in IPL_TEAMS or
                     match_info["team2"]["teamName"] in IPL_TEAMS)):
                    return {
                        "match_id": match_info["matchId"],
                        "team1": match_info["team1"]["teamName"],
                        "team2": match_info["team2"]["teamName"],
                        "venue": match_info["venueInfo"]["ground"],
                        "date": datetime.utcfromtimestamp(match_info["startDate"] / 1000).isoformat()
                    }
    logger.info("No IPL match found for today")
    return None

def get_match_by_date(date_str: str):
    date_requested = datetime.strptime(date_str, "%Y-%m-%d").strftime("%a, %d %b %Y")
    matches = fetch_series_matches()

    for match in matches:
        info = match.get("matchInfo", match)
        match_date = datetime.utcfromtimestamp(int(info["startDate"]) / 1000).strftime("%a, %d %b %Y")
        if match_date == date_requested and info["matchFormat"] == "T20":
            return {
                "match_id": info["matchId"],
                "team1": info["team1"]["teamName"],
                "team2": info["team2"]["teamName"],
                "venue": info["venueInfo"]["ground"],
                "status": info["status"],
                "date": match_date
            }

    logger.info("No match found for this date")
    return None


# live_data_provider.py (only showing the corrected get_match_details)
def get_match_details(match_id):
    url = f"{BASE_URL}/match/{match_id}"
    cache_key = f"cb:match:{match_id}:info:v1"
    data = _cached_get_json(url, _headers_with_endpoint(MATCH_INFO_ENDPOINT), cache_key, MATCH_INFO_TTL)

    if isinstance(data, dict) and data.get("_error"):
        logger.error(f"Error fetching match details: {data.get('_error')}")
        return None

    data = data.get("matchInfo", {})
    if not data:
        logger.info("No match info available")

    toss_results = data.get("tossResults") or {}
    toss_winner = toss_results.get("tossWinnerName", "")
    toss_decision = toss_results.get("decision", "")

    team1 = data.get("team1", {})
    team2 = data.get("team2", {})

    squads = {}
    playing_xi = {}
    if team1 and team2:
        squads = {
            team1["name"]: [player["fullName"] for player in team1.get("playerDetails", [])],
            team2["name"]: [player["fullName"] for player in team2.get("playerDetails", [])],
        }

        playing_xi = {
            team1["name"]: [
                player["fullName"] for player in team1.get("playerDetails", []) if not player.get("substitute", True)
            ],
            team2["name"]: [
                player["fullName"] for player in team2.get("playerDetails", []) if not player.get("substitute", True)
            ],
        }

        if len(playing_xi[team1["name"]]) < 11:
            playing_xi[team1["name"]] = squads.get(team1["name"], [])
        if len(playing_xi[team2["name"]]) < 11:
            playing_xi[team2["name"]] = squads.get(team2["name"], [])

    scorecard_innings = []
    if SCORECARD_ENDPOINT:
        scorecard_url = f"{BASE_URL}/match/{match_id}/scorecard"
        scorecard_cache_key = f"cb:match:{match_id}:scorecard:v1"
        scorecard_data = _cached_get_json(
            scorecard_url,
            _headers_with_endpoint(SCORECARD_ENDPOINT),
            scorecard_cache_key,
            SCORECARD_TTL,
        )
        if isinstance(scorecard_data, dict) and not scorecard_data.get("_error"):
            for entry in scorecard_data.get("scorecard", []):
                innings_id = entry.get("inningsId") or entry.get("inningsid")
                team_name = entry.get("batTeamName") or entry.get("batteamname")
                runs = entry.get("score")
                wickets = entry.get("wickets")
                overs = entry.get("overs")
                if innings_id and team_name and runs is not None and wickets is not None and overs is not None:
                    scorecard_innings.append(
                        {
                            "inningsId": innings_id,
                            "batTeamName": team_name,
                            "score": runs,
                            "wickets": wickets,
                            "overs": overs,
                        }
                    )
        else:
            logger.info("Scorecard endpoint not available or returned error.")

    overs_url = f"{BASE_URL}/match/{match_id}/overs"
    overs_cache_key = f"cb:match:{match_id}:overs:0:v1"
    overs_data = _cached_get_json(overs_url, _headers_with_endpoint(MATCH_INFO_ENDPOINT), overs_cache_key, OVERS_TTL)

    innings = scorecard_innings or []
    powerplay = {}

    if isinstance(overs_data, dict) and not overs_data.get("_error"):
        match_score = overs_data.get("matchScoreDetails", {}).get("inningsScoreList", [])
        if match_score and not innings:
            innings = match_score
            logger.info(f"Innings data: {match_score}")

        pp_data = overs_data.get("ppData", {})
        logger.info(f"Raw ppData: {pp_data}")

        if match_score:
            for innings_entry in match_score:
                team_name = innings_entry["batTeamName"]
                overs = innings_entry["overs"]
                runs = innings_entry["score"]
                wickets = innings_entry["wickets"]

                if overs <= 6:
                    powerplay[team_name] = {"runs": runs, "wickets": wickets}
                    logger.info(f"Powerplay for {team_name} (overs <= 6): runs={runs}, wickets={wickets}")
                elif overs > 6:
                    pp_runs = pp_data.get("pp_1" if innings_entry["inningsId"] == 1 else "pp_2", {}).get("runsScored", 0)
                    if pp_runs:
                        powerplay[team_name] = {"runs": pp_runs, "wickets": 0}
                        logger.info(f"Powerplay for {team_name} from ppData: runs={pp_runs}, wickets=0")
                    else:
                        pp_runs = int(runs * 6 / overs)
                        pp_wickets = min(2, wickets)
                        powerplay[team_name] = {"runs": pp_runs, "wickets": pp_wickets}
                        logger.info(f"Estimated powerplay for {team_name}: runs={pp_runs}, wickets={pp_wickets}")

    logger.info(f"Final powerplay dict: {powerplay}")
    return {
        "toss_winner": toss_winner,
        "toss_decision": toss_decision,
        "venue": (data.get("venue") or {}).get("name", ""),
        "squads": squads,
        "playing_11": playing_xi,
        "team1": team1.get("name", ""),
        "team2": team2.get("name", ""),
        "innings": innings,
        "powerplay": powerplay
    }


def get_completed_match_details(match_id):
    """Fetch match details with 24h TTL — use only for matches known to be completed."""
    completed_key = f"cb:match:{match_id}:completed:v1"
    cached = cache.get(completed_key)
    if cached is not None:
        _inc_stat('cache_hits')
        return cached
    details = get_match_details(match_id)
    if details:
        cache.set(completed_key, details, COMPLETED_MATCH_TTL)
    return details


# Fetch live match data for given date (simplified for Cricbuzz API)
def fetch_live_data(date_str: str):
    url = f"{BASE_URL}/series/{SERIES_ID}"
    cache_key = f"cb:series:{SERIES_ID}:info:v1"
    data = _stale_cached_get_json(url, _headers_with_endpoint(SERIES_ENDPOINT), cache_key, SERIES_SCHEDULE_TTL, stale_ttl=3600)

    formatted_date = datetime.strptime(date_str, "%Y-%m-%d").strftime('%a, %d %b %Y')
    logger.info("Formatted date for match key: %s", formatted_date)
    match_details_days = data.get("matchDetails", [])
    matches_today = []

    for day in match_details_days:
        match_day = day.get("matchDetailsMap", {})
        key = match_day.get("key")
        if key == formatted_date:
            logger.info("Found match_day for %s", formatted_date)
            for match in match_day.get("match", []):
                match_info = match["matchInfo"]
                if (
                    match_info["matchFormat"] == "T20" and
                    (match_info["team1"]["teamName"] in IPL_TEAMS or match_info["team2"]["teamName"] in IPL_TEAMS)
                ):
                    matches_today.append(match_info)

    logger.info("Found %d IPL matches for %s", len(matches_today), date_str)
    return matches_today

def get_first_innings_score(date: str) -> int:
    match_info = get_match_by_date(date)
    if not match_info:
        logger.warning("No match info for date %s", date)
        return 0
    
    match_id = match_info.get("match_id")
    match_details = get_match_details(match_id)
    if not match_details:
        logger.warning("No match details for match_id %s", match_id)
        return 0

    innings = match_details.get("innings", [])
    if not innings:
        logger.warning("No innings data found for match %s", match_id)
        return 0

    # First innings will have the lower inningsId
    first_innings = min(innings, key=lambda x: x.get("inningsId", 1))
    return first_innings.get("score", 0)

def get_todays_matches(date_str: str):
    """Return all IPL T20 matches for a given date."""
    return fetch_live_data(date_str)


def get_match_context_by_number(date_str: str, match_number: int = 0):
    """Return specific match context by index from the day's matches."""
    matches = fetch_live_data(date_str)
    
    if match_number >= len(matches):
        raise IndexError(f"Only {len(matches)} matches found for {date_str}. match_number={match_number} is invalid.")
    
    match = matches[match_number]
    match_id = match["matchId"]
    
    match_details = get_match_details(match_id)
    if not match_details:
        raise ValueError(f"Could not load details for match_id: {match_id}")

    return {
        "match_id": match_id,
        "team1": match["team1"]["teamName"],
        "team2": match["team2"]["teamName"],
        "venue": match["venueInfo"]["ground"],
        "status": match.get("status", "Preview"),
        "date": datetime.utcfromtimestamp(match["startDate"] / 1000).strftime("%a, %d %b %Y"),
        "playing_11": match_details.get("playing_11", {}),
        "squads": match_details.get("squads", {}),
        "toss_winner": match_details.get("toss_winner", ""),
        "toss_decision": match_details.get("toss_decision", ""),
        "innings": match_details.get("innings", []),
        "powerplay": match_details.get("powerplay", {})
    }
