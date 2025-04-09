import os
import requests
from datetime import datetime
from dotenv import load_dotenv
import logging
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


load_dotenv()

BASE_URL = "https://Cricbuzz-Official-Cricket-API.proxy-production.allthingsdev.co"
API_HEADERS = {
    "x-apihub-key": os.getenv("CRICKETDATA_API_KEY"),
    "x-apihub-host": "Cricbuzz-Official-Cricket-API.allthingsdev.co"
}

IPL_TEAMS = [
    "Chennai Super Kings", "Mumbai Indians", "Rajasthan Royals",
    "Sunrisers Hyderabad", "Kolkata Knight Riders", "Gujarat Titans",
    "Lucknow Super Giants", "Royal Challengers Bengaluru", "Delhi Capitals",
    "Punjab Kings"
]

SERIES_ID = 9237

def fetch_series_matches():
    API_HEADERS["x-apihub-endpoint"] = "661c6b89-b558-41fa-9553-d0aca64fcb6f"
    url = f"{BASE_URL}/series/{SERIES_ID}"
    response = requests.get(url, headers=API_HEADERS)
    if response.status_code != 200:
        print(f"Error fetching series matches: {response.status_code}")
        return []

    data = response.json()
    matches = []
    for day in data.get("matchDetails", []):
        for match in day["matchDetailsMap"]["match"]:
            matches.append(match["matchInfo"])
    
    return matches


# Fetch today's IPL match from Cricbuzz API
def get_todays_match():
    today_str = datetime.utcnow().strftime('%a, %d %b %Y')
    API_HEADERS["x-apihub-endpoint"] = "661c6b89-b558-41fa-9553-d0aca64fcb6f"
    url = f"{BASE_URL}/series/{SERIES_ID}"
    response = requests.get(url, headers=API_HEADERS)

    if response.status_code != 200:
        print(f"❌ Error fetching today's matches: {response.status_code}")
        return None

    match_maps = response.json().get("matchDetailsMap", [])
   
    for match_day in match_maps:
        if match_day['key'] == today_str:
            for match in match_day['match']:
                match_info = match["matchInfo"]
                if (match_info['matchFormat'] == 'T20' and
                    (match_info['team1']['teamName'] in IPL_TEAMS or
                     match_info['team2']['teamName'] in IPL_TEAMS)):
                    return {
                        "match_id": match_info["matchId"],
                        "team1": match_info["team1"]["teamName"],
                        "team2": match_info["team2"]["teamName"],
                        "venue": match_info["venueInfo"]["ground"],
                        "date": datetime.utcfromtimestamp(match_info["startDate"] / 1000).isoformat()
                    }
    print("⚠️ No IPL match found for today.")
    return None

def get_match_by_date(date_str: str):
    date_requested = datetime.strptime(date_str, "%Y-%m-%d").strftime("%a, %d %b %Y")
    matches = fetch_series_matches()

    for match in matches:
        match_date = datetime.utcfromtimestamp(int(match["startDate"]) / 1000).strftime("%a, %d %b %Y")
        if match_date == date_requested and match["matchFormat"] == "T20":
            return {
                "match_id": match["matchId"],
                "team1": match["team1"]["teamName"],
                "team2": match["team2"]["teamName"],
                "venue": match["venueInfo"]["ground"],
                "status": match["status"],
                "date": match_date
            }

    print("No match found for this date.")
    return None


# live_data_provider.py (only showing the corrected get_match_details)
def get_match_details(match_id):
    API_HEADERS["x-apihub-endpoint"] = "ac951751-d311-4d23-8f18-353e75432353"
    url = f"{BASE_URL}/match/{match_id}"
    response = requests.get(url, headers=API_HEADERS)

    if response.status_code != 200:
        logger.error(f"Error fetching match details: {response.status_code}")
        return None

    data = response.json().get("matchInfo", {})
    if not data:
        logger.warning("No match data available")
        return None

    toss_winner = data["tossResults"].get("tossWinnerName", "")
    toss_decision = data["tossResults"].get("decision", "")

    squads = {
        data['team1']['name']: [player['fullName'] for player in data['team1']['playerDetails']],
        data['team2']['name']: [player['fullName'] for player in data['team2']['playerDetails']]
    }

    playing_xi = {
        data['team1']['name']: [
            player['fullName'] for player in data['team1']['playerDetails'] if not player.get('substitute', True)
        ],
        data['team2']['name']: [
            player['fullName'] for player in data['team2']['playerDetails'] if not player.get('substitute', True)
        ]
    }

    if len(playing_xi[data['team1']['name']]) < 11:
        playing_xi[data['team1']['name']] = squads[data['team1']['name']]
    if len(playing_xi[data['team2']['name']]) < 11:
        playing_xi[data['team2']['name']] = squads[data['team2']['name']]

    overs_url = f"{BASE_URL}/match/{match_id}/overs"
    overs_resp = requests.get(overs_url, headers=API_HEADERS)

    innings = {}
    powerplay = {}

    if overs_resp.status_code == 200:
        overs_data = overs_resp.json()
        match_score = overs_data.get("matchScoreDetails", {}).get("inningsScoreList", [])
        if match_score:
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
                
                # Powerplay logic
                if overs <= 6:
                    powerplay[team_name] = {"runs": runs, "wickets": wickets}
                    logger.info(f"Powerplay for {team_name} (overs <= 6): runs={runs}, wickets={wickets}")
                elif overs > 6:
                    # Estimate powerplay if no specific data from ppData
                    pp_runs = pp_data.get("pp_1" if innings_entry["inningsId"] == 1 else "pp_2", {}).get("runsScored", 0)
                    if pp_runs:
                        powerplay[team_name] = {"runs": pp_runs, "wickets": 0}
                        logger.info(f"Powerplay for {team_name} from ppData: runs={pp_runs}, wickets=0")
                    else:
                        # Fallback estimation
                        pp_runs = int(runs * 6 / overs)
                        pp_wickets = min(2, wickets)
                        powerplay[team_name] = {"runs": pp_runs, "wickets": pp_wickets}
                        logger.info(f"Estimated powerplay for {team_name}: runs={pp_runs}, wickets={pp_wickets}")

    logger.info(f"Final powerplay dict: {powerplay}")
    return {
        "toss_winner": toss_winner,
        "toss_decision": toss_decision,
        "venue": data["venue"]["name"],
        "squads": squads,
        "playing_11": playing_xi,
        "team1": data['team1']['name'],
        "team2": data['team2']['name'],
        "innings": innings,
        "powerplay": powerplay
    }

# Fetch live match data for given date (simplified for Cricbuzz API)
def fetch_live_data(date_str: str):
    API_HEADERS["x-apihub-endpoint"] = "661c6b89-b558-41fa-9553-d0aca64fcb6f"
    url = f"{BASE_URL}/series/{SERIES_ID}"
    response = requests.get(url, headers=API_HEADERS)

    if response.status_code != 200:
        print(f"❌ Error fetching matches: {response.status_code}")
        return []

    
    formatted_date = datetime.strptime(date_str, "%Y-%m-%d").strftime('%a, %d %b %Y')
    print(f"🔍 Formatted Date for Match Key: {formatted_date}")
    match_details_days = response.json().get("matchDetails", [])
    matches_today = []

    for day in match_details_days:
        match_day = day.get("matchDetailsMap", {})
        key = match_day.get("key")
        if key == formatted_date:
            print(f"✅ Found match_day for {formatted_date}")
            for match in match_day.get("match", []):
                match_info = match["matchInfo"]
                if (
                    match_info["matchFormat"] == "T20" and
                    (match_info["team1"]["teamName"] in IPL_TEAMS or match_info["team2"]["teamName"] in IPL_TEAMS)
                ):
                    matches_today.append(match_info)

    if matches_today:
        print(f"✅ Found {len(matches_today)} IPL matches for {date_str}")
    else:
        print(f"⚠️ No IPL matches found for {date_str}")

    return matches_today

def get_first_innings_score(date: str) -> int:
    match_info = get_match_by_date(date)
    if not match_info:
        print(f"⚠️ No match info for date {date}")
        return 0
    
    match_id = match_info.get("match_id")
    match_details = get_match_details(match_id)
    if not match_details:
        print(f"⚠️ No match details for match_id {match_id}")
        return 0

    innings = match_details.get("innings", [])
    if not innings:
        print(f"⚠️ No innings data found for match {match_id}")
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


