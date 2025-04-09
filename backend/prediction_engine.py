# prediction_engine.py

import pandas as pd
import re
import random
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
from openai import OpenAI
import os
from typing import Optional, List, Dict, Tuple
from dotenv import load_dotenv
import pytz
from datetime import datetime
from backend.live_data_provider import get_todays_match,get_match_details
from backend.live_data_provider import fetch_live_data, IPL_TEAMS
from backend.utils import get_gmt_window

load_dotenv()

client = OpenAI()
# In-memory store for live match context
match_context = {}
live_match_state = {}

# This will now hold both static schedule and live match contexts
match_schedule = []


def normalize_date(date_str: str) -> str:
    return datetime.strptime(date_str, "%Y-%m-%d").date().isoformat()

def load_schedule_if_available():
    global match_schedule
    try:
        df = pd.read_csv("backend/scheduler_ipl_2025.csv")
        df.columns = [c.lower() for c in df.columns]
        df['date'] = df['date'].apply(normalize_date)
        match_schedule = df.to_dict(orient="records")
        print("📅 Schedule loaded with", len(match_schedule), "matches.")
    except Exception as e:
        print("⚠️ Failed to load static schedule:", e)
        match_schedule = []

def append_live_match_to_schedule(match_data: Dict):
    global match_schedule
    existing_dates = {m["date"] for m in match_schedule}
    match_date = normalize_date(match_data["date"])
    if match_date not in existing_dates:
        match_schedule.append({
            "date": match_date,
            "team1": match_data["team1"],
            "team2": match_data["team2"],
            "venue": match_data["venue"]
        })
        print(f"🆕 Appended live match for {match_date} to schedule")

def get_today_match(date: Optional[str] = None) -> Optional[Dict]:
    target_date = normalize_date(date) if date else datetime.today().date().isoformat()
    
    for match in match_schedule:
        if match.get("date") == target_date:
            return match

    # Try live data if not found in preloaded schedule
    print(f"🔍 Not found in schedule. Checking live API for {target_date}...")
    live_match = get_todays_match()
    if live_match and normalize_date(live_match["date"]) == target_date:
        append_live_match_to_schedule(live_match)
        return live_match
    
    return None

def load_2025_mock_data():
    df = pd.DataFrame([
        {
            "date": "2025-03-23",
            "team1": "Chennai Super Kings",
            "team2": "Mumbai Indians",
            "venue": "MA Chidambaram Stadium, Chennai"
        },
        {
            "date": "2025-03-24",
            "team1": "Royal Challengers Bangalore",
            "team2": "Delhi Capitals",
            "venue": "M. Chinnaswamy Stadium, Bengaluru"
        }
    ])
    return df.to_dict(orient="records")

def load_ipl_data():
    try:
        matches_df = pd.read_csv('backend/matches.csv')
        deliveries_df = pd.read_csv('backend/deliveries.csv', encoding='utf-8')

        # Ensure season is a string and handle NaNs explicitly
        matches_df['season'] = matches_df['season'].fillna('').astype(str)
        matches_df['season_year'] = matches_df['season'].str[:4]

        # Filter recent matches
        recent_matches_df = matches_df[matches_df['season_year'].isin(['2021','2022', '2023', '2024'])].copy()

        # Explicitly ensure these columns are strings and handle NaNs safely
        cols_to_normalize = ['venue', 'team1', 'team2', 'winner']
        for col in cols_to_normalize:
            recent_matches_df[col] = recent_matches_df[col].fillna('').astype(str).str.strip().str.lower()

        # Apply normalization clearly
        venue_normalization_map = {
            "ma chidambaram stadium, chepauk, chennai": "ma chidambaram stadium",
            "wankhede stadium, mumbai": "wankhede stadium",
            "dr dy patil sports academy, mumbai": "dr dy patil sports academy",
            "eden gardens, kolkata": "eden gardens",
            "narendra modi stadium, ahmedabad": "narendra modi stadium",
            "rajiv gandhi international stadium, uppal, hyderabad": "rajiv gandhi international stadium",
            "m chinnaswamy stadium, bengaluru": "m chinnaswamy stadium",
            "arun jaitley stadium, delhi": "arun jaitley stadium",
            "barsapara cricket stadium, guwahati": "barsapara cricket stadium",
            "sawai mansingh stadium, jaipur": "sawai mansingh stadium",
            "himachal pradesh cricket association stadium, dharamsala": "hpca cricket stadium",
            "maharaja yadavindra singh international cricket stadium, mullanpur": "maharaja yadavindra singh international cricket stadium",
            "dr. y.s. rajasekhara reddy aca-vdca cricket stadium, visakhapatnam": "aca-vdca cricket stadium",
            "punjab cricket association is bindra stadium, mohali, chandigarh": "is bindra stadium",
            "bharat ratna shri atal bihari vajpayee ekana cricket stadium, lucknow": "brsabv ekana cricket stadium",
            "brabourne stadium, mumbai": "brabourne stadium"
        }
        recent_matches_df['venue'] = recent_matches_df['venue'].replace(venue_normalization_map)

        # Correctly filter deliveries based on recent matches
        recent_deliveries_df = deliveries_df[deliveries_df['match_id'].isin(recent_matches_df['id'])].copy()

        logger.info(f"Loaded {len(recent_matches_df)} recent matches and {len(recent_deliveries_df)} deliveries with normalized data.")
        return recent_matches_df, recent_deliveries_df

    except Exception as e:
        logger.error(f"Error loading data: {e}")
        return None, None


def normalize_team_name(name: str | None) -> str:
    if not name:
        print("⚠️ Warning: normalize_team_name called with None or empty string")
        return ""

    name = name.strip().lower().replace(" ", "")

    # Handle abbreviations
    abbreviations = {
        "rcb": "royalchallengersbengaluru",
        "mi": "mumbaiindians",
        "csk": "chennaisuperkings",
        "dc": "delhicapitals",
        "kkr": "kolkataknightriders",
        "srh": "sunrisershyderabad",
        "gt": "gujarattitans",
        "pbks": "punjabkings",
        "rr": "rajasthanroyals",
        "lsg": "lucknowsupergiants"
    }

    # Fix common typos
    name = name.replace("&", "and")
    name = name.replace("punjabkingsxi", "punjabkings")
    name = name.replace("royalchallengersbengaluruu", "royalchallengersbengaluru")
    name = name.replace("delhicapitalss", "delhicapitals")

    return abbreviations.get(name, name)


# Load data at startup
recent_matches_df, recent_deliveries_df = load_ipl_data()
def update_match_context(date, toss_winner, toss_decision,status, playing_11=None, venue=None, team1=None, team2=None, squads=None):
    match_context[date] = {
       "team1": team1,
        "team2": team2,
        "venue": venue,
        "status": status,  # newly added
        "toss_winner": toss_winner,
        "toss_decision": toss_decision,
        "playing_11": playing_11,
        "squads": squads
    }

def get_match_context(date):
    return match_context.get(date)

match_contexts = {}

def calculate_recent_form(team, matches_df, n_matches=5):
    """Calculate recent form based on last n matches (win rate)."""
    recent_matches = matches_df[(matches_df['team1'] == team) | (matches_df['team2'] == team)].tail(n_matches)
    wins = len(recent_matches[recent_matches['winner'] == team])
    return wins / n_matches if recent_matches.shape[0] > 0 else 0.5

def calculate_team_stats(team, venue, matches_df, deliveries_df):
    """Calculate team-specific stats at the given venue with recent data."""
    avg_score = 170
    if 'venue' in matches_df.columns:
        venue_matches = matches_df[matches_df['venue'] == venue]
    else:
        venue_matches = matches_df
    
    match_ids = venue_matches['id'].tolist() if 'id' in venue_matches.columns else []
    
    team_matches = venue_matches[(venue_matches['team1'] == team) | (venue_matches['team2'] == team)]
    team_wins = len(team_matches[team_matches['winner'] == team]) if 'winner' in team_matches.columns else 0
    team_total = len(team_matches)
    win_rate = team_wins / team_total if team_total > 0 else 0.5
    
    recent_team_venue_matches = team_matches.tail(10)

    if not recent_team_venue_matches.empty and 'target_runs' in recent_team_venue_matches.columns:
        avg_score = recent_team_venue_matches['target_runs'].dropna().mean()
    if pd.isna(avg_score):
        avg_score = 170
    else:
        avg_score = 170

    avg_wickets = 7
    avg_pp_runs = 45
    avg_pp_wickets = 2
    
    if deliveries_df is not None and match_ids:
        venue_deliveries = deliveries_df[deliveries_df['match_id'].isin(match_ids)]
        team_deliveries = venue_deliveries[venue_deliveries['batting_team'] == team]
        
        print(f"Debug: {team} Matches at {venue}: {len(team_matches)}")
        print(f"Debug: {team} Deliveries at {venue}: {len(team_deliveries)}")
        
        wickets = team_deliveries[team_deliveries['player_dismissed'].notna()]
        wickets_per_innings = wickets.groupby(['match_id', 'inning']).size().mean()
        avg_wickets = wickets_per_innings if not pd.isna(wickets_per_innings) else 7
        
        pp_deliveries = team_deliveries[team_deliveries['over'] <= 6]
        print(f"Debug: {team} Power Play Deliveries at {venue}: {len(pp_deliveries)}")
        pp_runs_sum = pp_deliveries['total_runs'].sum()
        print(f"Debug: {team} Power Play Total Runs at {venue}: {pp_runs_sum}")
        avg_pp_runs = pp_deliveries.groupby(['match_id', 'inning'])['total_runs'].sum().mean() if not pp_deliveries.empty else 45
        pp_wickets = pp_deliveries[pp_deliveries['player_dismissed'].notna()].groupby(['match_id', 'inning']).size().mean()
        avg_pp_wickets = pp_wickets if not pd.isna(pp_wickets) else 2
    
    return {
        'win_rate': win_rate,
        'avg_score': avg_score,
        'avg_wickets': avg_wickets,
        'avg_pp_runs': avg_pp_runs,
        'avg_pp_wickets': avg_pp_wickets
    }

def calculate_bowler_impact(team, venue, deliveries_df, matches_df):
    """Calculate bowler impact score for the team at the given venue."""
    if 'venue' in matches_df.columns:
        venue_matches = matches_df[matches_df['venue'] == venue]
    else:
        venue_matches = matches_df
    
    match_ids = venue_matches['id'].tolist() if 'id' in venue_matches.columns else []
    team_deliveries = deliveries_df[deliveries_df['match_id'].isin(match_ids) & 
                                    (deliveries_df['bowling_team'] == team)]
    
    bowler_stats = team_deliveries.groupby('bowler').agg({
        'ball': 'count',
        'total_runs': 'sum',
        'player_dismissed': lambda x: x.notna().sum()
    }).reset_index()
    bowler_stats['overs'] = bowler_stats['ball'] / 6
    bowler_stats['economy'] = bowler_stats['total_runs'] / bowler_stats['overs']
    bowler_stats['wickets_per_over'] = bowler_stats['player_dismissed'] / bowler_stats['overs']
    
    top_bowlers = bowler_stats.nlargest(5, 'overs')
    if top_bowlers.empty:
        print(f"Debug: {team} No bowler data at {venue}, defaulting to 5.0")
        return 5.0
    
    avg_economy = top_bowlers['economy'].mean()
    avg_wickets_per_over = top_bowlers['wickets_per_over'].mean()
    economy_score = max(0, min(10, 10 - (avg_economy - 5)))
    wickets_score = max(0, min(5, avg_wickets_per_over * 5))
    impact_score = (economy_score + wickets_score) / 1.5
    print(f"Debug: {team} Bowler Impact at {venue} - Economy: {avg_economy}, Wickets/Over: {avg_wickets_per_over}, Score: {impact_score}")
    return max(0.0, min(10.0, impact_score))

def predict_winner_pre_toss(team1, team2, venue, matches_df=recent_matches_df, deliveries_df=recent_deliveries_df):
    logger.info(f"Predicting pre-toss winner for: {team1} vs {team2} at {venue}")

    team1_clean = normalize_team_name(team1)
    team2_clean = normalize_team_name(team2)
    venue_clean = venue.strip().lower()

    logger.info(f"Normalized names: team1='{team1_clean}', team2='{team2_clean}', venue='{venue_clean}'")

    # Head-to-Head
    h2h_matches = matches_df[
        ((matches_df['team1'] == team1_clean) & (matches_df['team2'] == team2_clean)) |
        ((matches_df['team1'] == team2_clean) & (matches_df['team2'] == team1_clean))
    ]
    team1_h2h_wins = len(h2h_matches[h2h_matches['winner'] == team1_clean])
    h2h_total_matches = len(h2h_matches)
    h2h_prob_team1 = (team1_h2h_wins / h2h_total_matches) if h2h_total_matches else 0.5

    logger.info(f"H2H: team1_wins={team1_h2h_wins}, total_h2h_matches={h2h_total_matches}, h2h_prob_team1={h2h_prob_team1:.2f}")

    # Recent form
    team1_recent_form = calculate_recent_form(team1_clean, matches_df)
    team2_recent_form = calculate_recent_form(team2_clean, matches_df)


    recent_form_adjustment = (team1_recent_form - team2_recent_form) * 0.5 + 0.5

    # Weighted final probability
    win_prob_team1 = (0.7 * recent_form_adjustment) + (0.3 * h2h_prob_team1)
    win_prob_team1 = max(0.05, min(0.95, win_prob_team1))

    logger.info(f"Final pre-toss win probability for {team1_clean}: {win_prob_team1:.2f}")

    return {
        team1: round(win_prob_team1 * 100, 1),
        team2: round((1 - win_prob_team1) * 100, 1)
    }

def predict_winner_post_toss(team1, team2, venue, toss_winner, toss_decision,
                             matches_df=recent_matches_df, deliveries_df=recent_deliveries_df):

    pre_toss_prediction = predict_winner_pre_toss(team1, team2, venue, matches_df, deliveries_df)
    pre_prob_team1 = pre_toss_prediction[team1] / 100

    chase_probability = get_dynamic_venue_chase_probability(venue, matches_df)

    toss_advantage = (chase_probability - 0.5) * 0.2
    if toss_winner == team1:
        team1_prob = pre_prob_team1 + (toss_advantage if toss_decision == 'field' else -toss_advantage)
    else:
        team1_prob = pre_prob_team1 - (toss_advantage if toss_decision == 'field' else -toss_advantage)

    # Bowler Impact adjustment (only post toss with confirmed XI)
    team1_bowler_impact = calculate_bowler_impact(team1, venue, deliveries_df, matches_df)
    team2_bowler_impact = calculate_bowler_impact(team2, venue, deliveries_df, matches_df)

    bowler_adjustment = (team2_bowler_impact - team1_bowler_impact) * 0.005
    team1_prob += bowler_adjustment

    # Final probability clamping
    team1_prob = max(0.05, min(0.95, team1_prob))

    return {
        team1: round(team1_prob * 100, 1),
        team2: round((1 - team1_prob) * 100, 1)
    }



def predict_score(team, venue, batting_first, opponent=None, date=None, matches_df=recent_matches_df, deliveries_df=recent_deliveries_df):
    context = get_match_context(date or datetime.today().date().isoformat())
    playing_xi = context.get('playing_11', {}).get(team, []) if context else []

    team_stats = calculate_team_stats(team, venue, matches_df, deliveries_df)
    batsmen_quality_factor = calculate_batting_strength(playing_xi, deliveries_df)
    base_score = team_stats['avg_score']
    adjusted_score = base_score * batsmen_quality_factor

    toss_winner = toss_decision = None
    if context:
        context_teams = context.get('teams')
        if context_teams and team in context_teams:
            opponent = context_teams[0] if team == context_teams[1] else context_teams[1]
            toss_winner = context.get('toss_winner')
            toss_decision = context.get('toss_decision')
        else:
            print(f"⚠️ Context found but 'teams' is missing or invalid: {context}")
    else:
        print("⚠️ No context found. Defaulting values.")

    opponent = opponent or 'Unknown'

    venue_multipliers = {
        'narendra modi stadium': 1.02,
        'eden gardens': 1.06,
        'brsabv ekana cricket stadium': 1.00,
        'rajiv gandhi international cricket stadium': 1.10,
        'm. a. chidambaram stadium': 0.95,
        'm. chinnaswamy stadium': 1.08,
        'wankhede stadium': 1.05,
        'arun jaitley stadium': 1.03,
        'sawai mansingh stadium': 0.98,
        'maharaja yadavindra singh international cricket stadium': 1.01,
        'aca-vdca cricket stadium': 1.00,
        'barsapara cricket stadium': 1.04,
        'hpca cricket stadium': 0.97
    }
    venue_adj = venue_multipliers.get(venue.lower(), 1.0)

    bowler_impact = calculate_bowler_impact(opponent, venue, deliveries_df, matches_df) if opponent != 'Unknown' else 5.0
    bowling_adj = 1 - (bowler_impact * 0.015)
    batting_adj = 1.05 if batting_first else 1.0

    if toss_winner and toss_decision and opponent != 'Unknown':
        win_probs = predict_winner_post_toss(team, opponent, venue, toss_winner, toss_decision, matches_df, deliveries_df)
    else:
        win_probs = predict_winner_pre_toss(team, opponent, venue, matches_df, deliveries_df)

    win_prob = win_probs.get(team, 50) / 100
    win_adj = 1 + (win_prob - 0.5) * 0.3

    final_score = adjusted_score * venue_adj * bowling_adj * batting_adj * win_adj
    final_score = final_score if not pd.isna(final_score) else 170

    print(f"🧮 Debug [{team}] ➜ Base: {base_score:.2f}, Batting QF: {batsmen_quality_factor:.2f}, Adjusted: {adjusted_score:.2f}, "
          f"Venue: {venue_adj}, Bowling: {bowling_adj:.3f}, BattingAdj: {batting_adj}, WinAdj: {win_adj:.3f}, Final: {final_score:.2f}")

    return f"{team} Score Prediction: {int(final_score - 7.5)}-{int(final_score + 7.5)} runs"
   

def calculate_batting_strength(players, deliveries_df):
    """Estimate batting strength based on recent performance of playing XI."""
    if 'batter' in deliveries_df.columns:
        batsman_col = 'batter'
    elif 'batsman' in deliveries_df.columns:
        batsman_col = 'batsman'
    elif 'striker' in deliveries_df.columns:
        batsman_col = 'striker'
    else:
        print("❌ Error: No valid batter column found in deliveries_df")
        return 1.0  # fallback

    recent_batting = deliveries_df[deliveries_df[batsman_col].isin(players)]
    if recent_batting.empty:
        print("⚠️ No batting data found for given players")
        return 1.0

    runs_per_batsman = recent_batting.groupby(batsman_col)['batsman_runs'].sum()
    balls_faced = recent_batting.groupby(batsman_col).size()
    strike_rates = (runs_per_batsman / balls_faced) * 100
    avg_sr = strike_rates.mean()

    # Normalize: use 130 as average SR
    quality_factor = avg_sr / 130 if not pd.isna(avg_sr) else 1.0
    return round(quality_factor, 2)

def calculate_team_recent_wickets(team, matches_df, deliveries_df, recent_n=5):
    # Get recent matches for this team (batting side)
    recent_matches = matches_df[
        (matches_df['team1'] == team) | (matches_df['team2'] == team)
    ].sort_values(by='date', ascending=False).head(recent_n)

    if recent_matches.empty:
        return 7.0  # fallback

    recent_match_ids = recent_matches['id'].tolist()

    team_deliveries = deliveries_df[
        (deliveries_df['match_id'].isin(recent_match_ids)) & 
        (deliveries_df['batting_team'] == team)
    ]

    if team_deliveries.empty:
        return 7.0

    # Count dismissals per innings
    dismissals = team_deliveries[team_deliveries['player_dismissed'].notna()]
    wickets_per_innings = dismissals.groupby(['match_id', 'inning']).size()

    return wickets_per_innings.mean() if not wickets_per_innings.empty else 7.0

def predict_wickets(team, venue, opponent=None, matches_df=recent_matches_df, deliveries_df=recent_deliveries_df):
    current_time = datetime.now(pytz.UTC)
    context = get_match_context(datetime.today().date().isoformat())

    if context and team in context.get('teams', []):
        opponent = context['teams'][0] if team == context['teams'][1] else context['teams'][1]
        toss_winner = context.get('toss_winner')
        toss_decision = context.get('toss_decision')
        playing_xi_opponent = context.get('playing_11', {}).get(opponent, [])
        match_date_str = context.get('date', datetime.today().isoformat())
        try:
            match_start = datetime.strptime(match_date_str, "%Y-%m-%dT%H:%M:%S.%f").replace(tzinfo=pytz.UTC)
        except ValueError:
            match_start = current_time
    else:
        opponent = opponent or 'Unknown'
        toss_winner = None
        toss_decision = None
        playing_xi_opponent = []
        match_start = current_time

    bowling_quality_factor = calculate_bowling_strength(playing_xi_opponent, deliveries_df)

    team_stats = calculate_team_stats(team, venue, matches_df, deliveries_df)
    recent_wickets = calculate_team_recent_wickets(team, matches_df, deliveries_df)
    base_wickets = (team_stats['avg_wickets'] + recent_wickets) / 2


    bowler_impact = calculate_bowler_impact(opponent, venue, deliveries_df, matches_df) if opponent != 'Unknown' else 5.0
    wickets_adj = bowler_impact * 0.3

    venue_wicket_adj = {
        'narendra modi stadium': 0.0,
        'eden gardens': -0.3,
        'brsabv ekana cricket stadium': 0.0,
        'rajiv gandhi international cricket stadium': -0.5,
        'm. a. chidambaram stadium': 0.5,
        'm. chinnaswamy stadium': -0.4,
        'wankhede stadium': -0.3,
        'arun jaitley stadium': 0.2,
        'sawai mansingh stadium': 0.4,
        'maharaja yadavindra singh international cricket stadium': 0.1,
        'aca-vdca cricket stadium': 0.0,
        'barsapara cricket stadium': -0.2,
        'hpca cricket stadium': 0.3
    }
    venue_adj = venue_wicket_adj.get(venue.lower(), 0.0)

    if toss_winner and toss_decision and opponent != 'Unknown':
        win_probs = predict_winner_post_toss(team, opponent, venue, toss_winner, toss_decision, matches_df, deliveries_df)
    else:
        win_probs = predict_winner_pre_toss(team, opponent, venue, matches_df, deliveries_df)
    win_prob = win_probs.get(team, 50) / 100
    win_adj = (win_prob - 0.5) * 1.0

    final_wickets = base_wickets + wickets_adj + venue_adj + win_adj
    final_wickets *= bowling_quality_factor

    # ✅ Add jitter only if we’re in pre-match context (i.e., not live)
    if context:
        jitter = random.uniform(-0.6, 0.6)
        print(f"🔀 Adding jitter for {team}: {jitter:.2f}")
        final_wickets += jitter


    final_wickets = max(0, min(10, final_wickets if not pd.isna(final_wickets) else 7))

    print(f"Debug: {team} Wickets - Base: {base_wickets:.2f}, Bowler Adj: {wickets_adj:.2f}, Venue Adj: {venue_adj:.2f}, "
          f"Win Adj: {win_adj:.2f}, Bowling XI Factor: {bowling_quality_factor:.2f}, Final: {final_wickets:.2f}")

    return f"{team} Wickets Prediction: {max(0, int(final_wickets - 1))}-{min(10, int(final_wickets + 1))} wickets"


def calculate_bowling_strength(players, deliveries_df):
    if not players:
        return 1.0

    recent_bowling = deliveries_df[deliveries_df['bowler'].isin(players)]
    wickets_taken = recent_bowling['player_dismissed'].count()
    overs_bowled = len(recent_bowling) / 6
    wickets_per_over = wickets_taken / overs_bowled if overs_bowled > 0 else 0.15
    factor = min(max(wickets_per_over / 0.15, 0.8), 1.2)  # baseline wickets per over as 0.15

    return factor

def calculate_team_recent_powerplay(team, deliveries_df, matches_df, recent_n=5):
    recent_matches = matches_df[
        (matches_df['team1'] == team) | (matches_df['team2'] == team)
    ].sort_values(by='date', ascending=False).head(recent_n)

    if recent_matches.empty:
        return 45, 2

    recent_ids = recent_matches['id'].tolist()
    team_pp_deliveries = deliveries_df[
        (deliveries_df['match_id'].isin(recent_ids)) &
        (deliveries_df['batting_team'] == team) &
        (deliveries_df['over'] <= 6)
    ]

    if team_pp_deliveries.empty:
        return 45, 2

    runs = team_pp_deliveries.groupby(['match_id'])['total_runs'].sum()
    wickets = team_pp_deliveries[team_pp_deliveries['player_dismissed'].notna()].groupby(['match_id']).size()

    avg_runs = runs.mean() if not runs.empty else 45
    avg_wkts = wickets.mean() if not wickets.empty else 2

    return avg_runs, avg_wkts


def predict_power_play(team, venue, matches_df=recent_matches_df, deliveries_df=recent_deliveries_df, date=None):
    """Predict power play runs and wickets with opponent bowling impact and match phase."""
    current_time = datetime.now(pytz.UTC)
    match_start = current_time
    context = get_match_context(date or datetime.today().date().isoformat())
    
    # Normalize names for safe comparison
    team_clean = team.strip().lower()
    team1 = context.get("team1", "").strip()
    team2 = context.get("team2", "").strip()
    toss_winner = context.get("toss_winner")
    toss_decision = context.get("toss_decision")

    opponent = 'Unknown'
    if team.strip() == team1:
        opponent = team2
    elif team.strip() == team2:
        opponent = team1
        toss_winner = context.get('toss_winner')
        toss_decision = context.get('toss_decision')
        match_date_str = context.get('date', datetime.today().isoformat())
        try:
            match_start = datetime.strptime(match_date_str, "%Y-%m-%dT%H:%M:%S.%f").replace(tzinfo=pytz.UTC)
        except ValueError:
            try:
                match_start = datetime.strptime(match_date_str, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=pytz.UTC)
            except ValueError:
                match_start = current_time
    else:
        match_start = current_time

    # Stats
    team_stats = calculate_team_stats(team, venue, matches_df, deliveries_df)
    recent_pp_runs, recent_pp_wkts = calculate_team_recent_powerplay(team, deliveries_df, matches_df)
    avg_pp_runs = (team_stats['avg_pp_runs'] + recent_pp_runs) / 2
    avg_pp_wickets = (team_stats['avg_pp_wickets'] + recent_pp_wkts) / 2


    # Bowling impact
    bowler_impact = calculate_bowler_impact(opponent, venue, deliveries_df, matches_df) if opponent != 'Unknown' else 5.0
    pp_wickets_adj = bowler_impact * 0.3
    pp_runs_adj_bowler = 1 - (bowler_impact * 0.03)

    # Win probability
    if toss_winner and toss_decision and opponent != 'Unknown':
        win_probs = predict_winner_post_toss(team, opponent, venue, toss_winner, toss_decision, matches_df, deliveries_df)
    else:
        win_probs = predict_winner_pre_toss(team, opponent, venue, matches_df, deliveries_df)

    win_prob = win_probs.get(team, 50) / 100
    win_runs_adj = 1 + (win_prob - 0.5) * 0.2
    win_wickets_adj = (win_prob - 0.5) * -1.0

    # Venue adj
    venue_pp_adj = {
        'narendra modi stadium': 1.02,
        'eden gardens': 1.06,
        'brsabv ekana cricket stadium': 1.00,
        'rajiv gandhi international cricket stadium': 1.10,
        'm. a. chidambaram stadium': 0.95,
        'm. chinnaswamy stadium': 1.08,
        'wankhede stadium': 1.05,
        'arun jaitley stadium': 1.03,
        'sawai mansingh stadium': 0.98,
        'maharaja yadavindra singh international cricket stadium': 1.01,
        'aca-vdca cricket stadium': 1.00,
        'barsapara cricket stadium': 1.04,
        'hpca cricket stadium': 0.97
    }
    pp_runs_venue_adj = venue_pp_adj.get(venue.lower(), 1.0)

    # Phase-based
    live_state = get_live_match_state(date or datetime.today().date().isoformat())
    if current_time < match_start:
        final_pp_runs = avg_pp_runs * pp_runs_venue_adj * pp_runs_adj_bowler * win_runs_adj
        final_pp_wickets = avg_pp_wickets + pp_wickets_adj + win_wickets_adj
        phase = "Pre-match"
    elif toss_winner and current_time >= match_start and not live_state.get('runs'):
        toss_runs_adj = 1.05 if (toss_winner == team and toss_decision == 'bat') else 1.0
        final_pp_runs = avg_pp_runs * pp_runs_venue_adj * pp_runs_adj_bowler * toss_runs_adj * win_runs_adj
        final_pp_wickets = avg_pp_wickets + pp_wickets_adj + (0.5 if toss_decision == 'field' else 0) + win_wickets_adj
        phase = "Post-toss"
    else:
        overs = live_state.get('overs', 0) or 0.1
        if overs <= 6:
            pp_runs = live_state.get(f"{team}_pp_runs", 0)
            pp_wickets = live_state.get(f"{team}_pp_wickets", 0)
            remaining_overs = 6 - overs
            runs_per_over = (avg_pp_runs * pp_runs_venue_adj * pp_runs_adj_bowler * win_runs_adj) / 6
            wickets_per_over = (avg_pp_wickets + pp_wickets_adj + win_wickets_adj) / 6
            final_pp_runs = pp_runs + (runs_per_over * remaining_overs)
            final_pp_wickets = pp_wickets + (wickets_per_over * remaining_overs)
        else:
            final_pp_runs = live_state.get(f"{team}_pp_runs", avg_pp_runs)
            final_pp_wickets = live_state.get(f"{team}_pp_wickets", avg_pp_wickets)
        phase = "In-match"
    # 🎲 Add jitter to differentiate predictions slightly
    jitter_runs = random.uniform(-1.5, 1.5)
    jitter_wickets = random.uniform(-0.3, 0.3)
    print(f"🔀 Adding jitter to {team} ➜ Runs: {jitter_runs:.2f}, Wickets: {jitter_wickets:.2f}")

    final_pp_runs += jitter_runs
    final_pp_wickets += jitter_wickets

    final_pp_runs = final_pp_runs if not pd.isna(final_pp_runs) else 45
    final_pp_wickets = max(0, min(6, final_pp_wickets if not pd.isna(final_pp_wickets) else 2))

    if phase in ["Pre-match", "Post-toss"]:
        jitter_runs = random.uniform(-1.5, 1.5)
        jitter_wkts = random.uniform(-0.3, 0.3)
        print(f"🔀 Adding jitter for {team}: Runs {jitter_runs:.2f}, Wickets {jitter_wkts:.2f}")
        final_pp_runs += jitter_runs
        final_pp_wickets += jitter_wkts
    # Over 50 prob
    over_50_prob = 0.5
    if phase != "In-match" and 'venue' in matches_df.columns:
        venue_matches = matches_df[matches_df['venue'] == venue]
        match_ids = venue_matches['id'].tolist()
        pp_deliveries = deliveries_df[(deliveries_df['match_id'].isin(match_ids)) &
                                      (deliveries_df['batting_team'] == team) &
                                      (deliveries_df['over'] <= 6)]
        pp_runs_per_match = pp_deliveries.groupby('match_id')['total_runs'].sum()
        over_50_prob = (pp_runs_per_match > 50).mean() if not pp_runs_per_match.empty else 0.5
    pp_run_low = round(final_pp_runs - 10)
    pp_run_high = round(final_pp_runs + 10)
    pp_wkts_low = max(0, round(final_pp_wickets - 1))
    pp_wkts_high = min(6, round(final_pp_wickets + 1))
    # 🧠 Debug Logs
    print(f"\n🧠 PowerPlay Prediction for: {team}")
    print(f"  ▸ Opponent: {opponent}")
    print(f"  ▸ Toss: {toss_winner} chose to {toss_decision}")
    print(f"  ▸ Win Prob: {win_prob:.2f}, Win Adj: {win_runs_adj:.2f}, Wicket Adj: {win_wickets_adj:.2f}")
    print(f"  ▸ Venue Adj: {pp_runs_venue_adj}, Bowler Impact: {bowler_impact}")
    print(f"  ▸ Final Runs: {final_pp_runs:.2f}, Final Wickets: {final_pp_wickets:.2f}, Phase: {phase}")

    return (f"{team} Power Play Prediction: {pp_run_low}-{pp_run_high} runs, "
        f"{pp_wkts_low}-{pp_wkts_high} wickets, "
        f"Over 50 runs: {round(over_50_prob * 100, 2)}%")

def load_2025_mock_data():
    """Mock IPL 2025 schedule and squads for testing."""
    schedule_2025 = pd.DataFrame({
        'date': ['2025-03-21'],
        'team1': ['Chennai Super Kings'],
        'team2': ['Mumbai Indians'],
        'venue': ['Wankhede Stadium']
    })

    squads_2025 = pd.DataFrame({
        'team': ['Chennai Super Kings']*2 + ['Mumbai Indians']*2,
        'player': ['Ruturaj Gaikwad', 'MS Dhoni', 'Hardik Pandya', 'Rohit Sharma']
    })

    return schedule_2025, squads_2025

def get_head_to_head_summary(team1, team2, matches_df):
    team1_clean = normalize_team_name(team1)
    team2_clean = normalize_team_name(team2)

    def match_filter(row):
        t1 = normalize_team_name(row["team1"])
        t2 = normalize_team_name(row["team2"])
        return (t1 == team1_clean and t2 == team2_clean) or (t1 == team2_clean and t2 == team1_clean)

    h2h_df = matches_df[matches_df.apply(match_filter, axis=1)]

    team1_wins = int((h2h_df["winner"].str.lower() == team1_clean).sum())
    team2_wins = int((h2h_df["winner"].str.lower() == team2_clean).sum())
    ties = int(h2h_df["winner"].isna().sum())

    return {
        "team1": team1,
        "team2": team2,
        "total_matches": int(len(h2h_df)),
        "team1_wins": team1_wins,
        "team2_wins": team2_wins,
        "ties_or_no_result": ties
    }

def get_venue_based_stats(team1, team2, venue, matches_df):
    team1 = team1.lower().strip()
    team2 = team2.lower().strip()
    venue = venue.lower().strip()

    df = matches_df.copy()
    df['team1'] = df['team1'].str.lower().str.strip()
    df['team2'] = df['team2'].str.lower().str.strip()
    df['venue'] = df['venue'].str.lower().str.strip()
    df['winner'] = df['winner'].fillna('no result').str.lower().str.strip()

    venue_matches = df[
        (((df['team1'] == team1) & (df['team2'] == team2)) |
         ((df['team1'] == team2) & (df['team2'] == team1))) &
        (df['venue'] == venue)
    ]

    total = len(venue_matches)
    team1_wins = (venue_matches['winner'] == team1).sum()
    team2_wins = (venue_matches['winner'] == team2).sum()
    ties_or_no_result = total - team1_wins - team2_wins

    return {
        "team1": team1,
        "team2": team2,
        "venue": venue,
        "total_matches": int(total),
        "team1_wins": int(team1_wins),
        "team2_wins": int(team2_wins),
        "ties_or_no_result": int(ties_or_no_result)
    }

def get_pre_match_context_summary(team1, team2, venue, matches_df):
    def normalize(text):
        return text.strip().lower()

    t1 = normalize(team1)
    t2 = normalize(team2)
    v = normalize(venue)

    matches_df = matches_df.copy()
    matches_df['team1'] = matches_df['team1'].fillna('').apply(normalize)
    matches_df['team2'] = matches_df['team2'].fillna('').apply(normalize)
    matches_df['winner'] = matches_df['winner'].fillna('').apply(normalize)
    matches_df['venue'] = matches_df['venue'].fillna('').apply(normalize)
    matches_df['toss_winner'] = matches_df['toss_winner'].fillna('').apply(normalize)
    matches_df['toss_decision'] = matches_df['toss_decision'].fillna('').apply(normalize)

    head_to_head = matches_df[
        ((matches_df['team1'] == t1) & (matches_df['team2'] == t2)) |
        ((matches_df['team1'] == t2) & (matches_df['team2'] == t1))
    ]
    total_matches = len(head_to_head)
    team1_wins = (head_to_head['winner'] == t1).sum()
    team2_wins = (head_to_head['winner'] == t2).sum()
    ties_or_no_result = total_matches - team1_wins - team2_wins

    venue_matches = head_to_head[head_to_head['venue'] == v]
    venue_total = len(venue_matches)
    venue_team1_wins = (venue_matches['winner'] == t1).sum()
    venue_team2_wins = (venue_matches['winner'] == t2).sum()
    venue_ties_or_no_result = venue_total - venue_team1_wins - venue_team2_wins

    toss_decisions = venue_matches.groupby(['toss_winner', 'toss_decision']).size().reset_index(name='count')

    return {
        "overall": {
            "total_matches": int(total_matches),
            f"{t1}_wins": int(team1_wins),
            f"{t2}_wins": int(team2_wins),
            "ties_or_no_result": int(ties_or_no_result)
        },
        "venue": {
            "venue": venue,
            "total_matches": int(venue_total),
            f"{t1}_wins": int(venue_team1_wins),
            f"{t2}_wins": int(venue_team2_wins),
            "ties_or_no_result": int(venue_ties_or_no_result)
        },
        "toss_decisions": toss_decisions.to_dict(orient="records")
    }

def get_full_match_context(date: str, matches_df, match_contexts):
    match_row = matches_df[matches_df["date"] == date]
    if match_row.empty:
        return {"error": f"No match found on {date}"}
    
    match_row = match_row.iloc[0]

    context = {
        "match": f"{match_row['team1']} vs {match_row['team2']}",
        "venue": match_row['venue'],
        "date": match_row['date'],
        "toss_winner": match_row['toss_winner'],
        "toss_decision": match_row['toss_decision'],
        "pitch_report": "Pitch report not available",
    }

    key = match_row['date']
    if key in match_contexts:
        context["playing_11"] = match_contexts[key].get("playing_11", {})
    else:
        context["playing_11"] = {}

    return context

def get_prediction_breakdown(team1, team2, venue, toss_winner, toss_decision, matches_df, deliveries_df):
    pre_toss = predict_winner_pre_toss(team1, team2, venue, matches_df, deliveries_df)
    pre_prob_team1 = pre_toss[team1]
    pre_prob_team2 = pre_toss[team2]

    venue_matches = matches_df[matches_df['venue'] == venue]
    recent_seasons = ['2022', '2023', '2024']
    venue_matches_recent = venue_matches[venue_matches['season_year'].isin(recent_seasons)]
    field_count_recent = len(venue_matches_recent[venue_matches_recent['toss_decision'] == 'field'])
    bat_count_recent = len(venue_matches_recent[venue_matches_recent['toss_decision'] == 'bat'])
    chase_wins_field_recent = len(venue_matches_recent[(venue_matches_recent['toss_decision'] == 'field') & 
                                                       (venue_matches_recent['winner'] != venue_matches_recent['toss_winner'])])
    chase_wins_bat_recent = len(venue_matches_recent[(venue_matches_recent['toss_decision'] == 'bat') & 
                                                     (venue_matches_recent['winner'] == venue_matches_recent['team2'])])
    chase_wins_recent = chase_wins_field_recent + chase_wins_bat_recent
    venue_total_recent = len(venue_matches_recent)
    chase_prob = chase_wins_recent / venue_total_recent if venue_total_recent else 0.5
    if venue == 'Wankhede Stadium':
        chase_prob = 0.65

    team1_bowler_impact = calculate_bowler_impact(team1, venue, deliveries_df, matches_df)
    team2_bowler_impact = calculate_bowler_impact(team2, venue, deliveries_df, matches_df)
    bowler_diff = team2_bowler_impact - team1_bowler_impact
    bowler_adjustment = bowler_diff * 0.5

    toss_adjustment = (chase_prob - 0.5) * 20
    total_adjustment = toss_adjustment + bowler_adjustment

    if toss_winner == team1 and toss_decision == 'field':
        post_prob_team1 = pre_prob_team1 + total_adjustment
    elif toss_winner == team2 and toss_decision == 'field':
        post_prob_team1 = pre_prob_team1 - total_adjustment
    elif toss_winner == team1 and toss_decision == 'bat':
        post_prob_team1 = pre_prob_team1 - total_adjustment
    elif toss_winner == team2 and toss_decision == 'bat':
        post_prob_team1 = pre_prob_team1 + total_adjustment
    else:
        post_prob_team1 = pre_prob_team1

    post_prob_team2 = 100 - post_prob_team1

    return {
        "team1": team1,
        "team2": team2,
        "head_to_head_probability": pre_prob_team1,
        "venue_chase_probability": round(chase_prob * 100, 1),
        "toss_impact_adjustment": round(toss_adjustment, 2),
        "bowler_impact_adjustment": round(bowler_adjustment, 2),
        "post_toss_probability": {
            team1: round(post_prob_team1, 1),
            team2: round(post_prob_team2, 1)
        }
    }

def get_team_stats_summary(team, venue, matches_df, deliveries_df):
    stats = calculate_team_stats(team, venue, matches_df, deliveries_df)
    return {
        "team": team,
        "venue": venue,
        "win_rate": round(stats['win_rate'] * 100, 1),
        "average_score": round(stats['avg_score'], 1),
        "average_wickets_lost": round(stats['avg_wickets'], 1),
        "average_powerplay_runs": round(stats['avg_pp_runs'], 1),
        "average_powerplay_wickets": round(stats['avg_pp_wickets'], 1)
    }

# prediction_engine.py (only the relevant part with logging)
def get_live_match_state(date: str):
    logger.info(f"Fetching live state for {date}")
    if date not in live_match_state or not live_match_state[date]:
        logger.info(f"State missing or empty for {date}, attempting to update")
        update_live_match_state(date)
    return live_match_state.get(date, {})

def update_live_match_state(date_str: str):
    logger.info(f"Updating live state for {date_str}")
    matches = fetch_live_data(date_str)
    if not matches:
        logger.warning(f"No matches found for {date_str}, preserving existing state if any")
        return  # Don’t reset to {}—preserve what /update-match-context set

    match_info = matches[0]
    match_id = match_info["matchId"]
    team1 = normalize_team_name(match_info["team1"]["teamName"])
    team2 = normalize_team_name(match_info["team2"]["teamName"])
    logger.info(f"Teams: {team1} vs {team2}")

    details = get_match_details(match_id)
    if not details:
        logger.warning(f"No match details for match_id {match_id}")
        return

    innings_data = details.get("innings", [])
    if not innings_data:
        toss_winner = details.get("toss_winner")
        toss_decision = details.get("toss_decision")
        if toss_winner and toss_decision:
            if toss_decision == "bat":
                first_innings_team = normalize_team_name(toss_winner)
            else:
                first_innings_team = team2 if normalize_team_name(toss_winner) == team1 else team1
            batting_team = first_innings_team
            runs = wickets = overs = 0
        else:
            batting_team = None
            first_innings_team = None
            runs = wickets = overs = 0
        logger.info(f"Toss-based fallback: batting={batting_team}, first_innings={first_innings_team}")
    else:
        current_innings = max(innings_data, key=lambda x: x.get("inningsId", 0), default=None)
        if not current_innings:
            logger.warning(f"No current innings for {date_str}")
            return
        batting_team = normalize_team_name(current_innings["batTeamName"])
        first_innings_team = normalize_team_name(innings_data[0]["batTeamName"]) if innings_data else batting_team
        runs = current_innings.get("score", 0)
        wickets = current_innings.get("wickets", 0)
        overs = current_innings.get("overs", 0)
        logger.info(f"Current state: batting={batting_team}, first_innings={first_innings_team}, runs={runs}, wickets={wickets}, overs={overs}")

    powerplay_data = details.get("powerplay", {})
    logger.info(f"Raw powerplay data: {powerplay_data}")
    normalized_powerplay = {normalize_team_name(k): v for k, v in powerplay_data.items()}
    logger.info(f"Normalized powerplay data: {normalized_powerplay}")

    team1_pp_runs = normalized_powerplay.get(team1, {}).get("runs", 0)
    team1_pp_wickets = normalized_powerplay.get(team1, {}).get("wickets", 0)
    team2_pp_runs = normalized_powerplay.get(team2, {}).get("runs", 0)
    team2_pp_wickets = normalized_powerplay.get(team2, {}).get("wickets", 0)
    logger.info(f"Powerplay assignments: {team1}_pp_runs={team1_pp_runs}, {team1}_pp_wickets={team1_pp_wickets}, {team2}_pp_runs={team2_pp_runs}, {team2}_pp_wickets={team2_pp_wickets}")

    live_match_state[date_str] = {
        "batting_team": batting_team,
        "first_innings_team": first_innings_team,
        "runs": runs,
        "wickets": wickets,
        "overs": overs,
        f"{team1}_pp_runs": team1_pp_runs,
        f"{team1}_pp_wickets": team1_pp_wickets,
        f"{team2}_pp_runs": team2_pp_runs,
        f"{team2}_pp_wickets": team2_pp_wickets
    }
    logger.info(f"Updated live state for {date_str}: {live_match_state[date_str]}")

def predict_powerplay_performance(team, venue, matches_df, deliveries_df):
    stats = calculate_team_stats(team, venue, matches_df, deliveries_df)
    runs = stats['avg_pp_runs']
    wickets = stats['avg_pp_wickets']
    return f"Powerplay Prediction for {team}: {int(runs - 10)}-{int(runs + 10)} runs, {int(wickets - 1)}-{int(wickets + 1)} wickets"

def predict_early_wicket_probability(team, deliveries_df, matches_df):
    match_ids = matches_df[(matches_df['team1'] == team) | (matches_df['team2'] == team)]['id'].unique()
    team_deliveries = deliveries_df[deliveries_df['match_id'].isin(match_ids) & (deliveries_df['batting_team'] == team)]

    first_wickets = []

    for match_id in match_ids:
        match_deliveries = team_deliveries[team_deliveries['match_id'] == match_id]
        dismissed = match_deliveries[match_deliveries['player_dismissed'].notna()]
        if not dismissed.empty:
            first_wicket_index = dismissed.index[0]
            runs_until_first_wicket = match_deliveries.loc[:first_wicket_index, 'total_runs'].sum()
            first_wickets.append(runs_until_first_wicket)

    if not first_wickets:
        return "No data available to estimate early wicket probability."

    before_30 = sum(1 for x in first_wickets if x < 30)
    total = len(first_wickets)
    percent = round((before_30 / total) * 100, 1)
    return f"Early Wicket Prediction: {percent}% of matches had the 1st wicket before 30 runs"

def handle_nlp_query(query: str, date: str, matches_df, deliveries_df):
    query = query.lower()
    context = get_match_context(date)
    live_state = get_live_match_state(date)

    if not context:
        return {"error": f"No match context found for date {date}"}

    team1 = context["team1"]
    team2 = context["team2"]
    venue = context["venue"]
    toss_winner = context.get("toss_winner")
    toss_decision = context.get("toss_decision")

    responses = []

    intent_patterns = [
        {
            "intent": "toss_result",
            "patterns": [r"who.*(toss)", r"which team.*won the toss"],
            "handler": lambda: {"toss_winner": toss_winner, "decision": toss_decision}
        },
        {
            "intent": "match_winner",
            "patterns": [r"who.*win", r"which team.*win"],
            "handler": lambda: predict_winner_post_toss(team1, team2, venue, toss_winner, toss_decision, matches_df, deliveries_df)
                if toss_winner and toss_decision else predict_winner_pre_toss(team1, team2, venue, matches_df, deliveries_df)
        },
        {
            "intent": "super_over_chance",
            "patterns": [r"super over"],
            "handler": lambda: {"super_over_possible": abs(live_state.get("target", 0) - live_state.get("runs", 0)) <= 5}
                if live_state.get("inning") == 2 else {"super_over_possible": "Too early to tell"}
        },
        {
            "intent": "boundaries",
            "patterns": [r"\b4s\b", r"\bfours\b", r"\b6s\b", r"\bsixes\b"],
            "handler": lambda: {
                team1: {"4s": 12, "6s": 6},
                team2: {"4s": 11, "6s": 9}
            }
        },
        {
            "intent": "total_score",
            "patterns": [r"total.*score", r"overall.*score", r"final.*score"],
            "handler": lambda: {
                "predicted_total_score_range": f"{predict_score(team1, venue, True, matches_df)} + {predict_score(team2, venue, False, matches_df)}"
            }
        },
        {
            "intent": "powerplay_performance",
            "patterns": [r"powerplay.*over 50", r"powerplay.*under 50"],
            "handler": lambda: {"powerplay_prediction": predict_power_play(
                live_state.get("batting_team", team1), venue,date, matches_df, deliveries_df)}
        },
        {
            "intent": "early_wicket",
            "patterns": [r"first wicket.*(before|after) 30"],
            "handler": lambda: {"first_wicket_range": "Likely between 20-40 runs"}
        },
        {
            "intent": "top3_batsman",
            "patterns": [r"top 3", r"first 3 batsmen", r"any batsman.*score"],
            "handler": lambda: {"batsman_to_score": "High chance one of top 3 will cross 50"}
        },
        {
            "intent": "total_wickets",
            "patterns": [r"how many.*wickets", r"total wickets"],
            "handler": lambda: {
                "wickets_prediction": [
                    predict_wickets(team1, venue, matches_df, deliveries_df),
                    predict_wickets(team2, venue, matches_df, deliveries_df)
                ]
            }
        }
    ]

    matched = False

    for intent in intent_patterns:
        for pattern in intent["patterns"]:
            if re.search(pattern, query):
                response = intent["handler"]()
                responses.append({
                    "intent": intent["intent"],
                    "result": response
                })
                matched = True
                break

    if not matched:
        return {"message": "Sorry, I didn't understand that question."}

    return responses

def generate_win_prediction(date: str, matches_df, deliveries_df):
    context = get_match_context(date)
    if not context:
        return {"error": f"No context found for date {date}. Please update context first."}

    # Normalizing team names explicitly
    team1 = normalize_team_name(context["team1"])
    team2 = normalize_team_name(context["team2"])

    # Normalizing venue name explicitly
    venue = context["venue"].strip().lower()

    toss_winner = context.get("toss_winner")
    toss_decision = context.get("toss_decision")

    if toss_winner and toss_decision:
        toss_winner = normalize_team_name(toss_winner)
        return predict_winner_post_toss(team1, team2, venue, toss_winner, toss_decision, matches_df, deliveries_df)
    else:
        return predict_winner_pre_toss(team1, team2, venue, matches_df, deliveries_df)

def get_dynamic_venue_chase_probability(venue, matches_df):
    recent_venue_matches = matches_df[matches_df['venue'].str.lower() == venue.lower()]
    recent_venue_matches = recent_venue_matches.tail(20)  # take most recent 20 matches at venue
    
    if recent_venue_matches.empty:
        return 0.5  # fallback

    chase_wins = recent_venue_matches[
        ((recent_venue_matches['toss_decision'] == 'field') & (recent_venue_matches['winner'] == recent_venue_matches['toss_winner'])) |
        ((recent_venue_matches['toss_decision'] == 'bat') & (recent_venue_matches['winner'] != recent_venue_matches['toss_winner']))
    ]
    chase_probability = len(chase_wins) / len(recent_venue_matches)
    return chase_probability

def generate_score_prediction(date: str, matches_df):
    context = get_match_context(date)
    if not context:
        return {"error": f"No context found for date {date}. Please update context first."}
    
    team1 = context["team1"]
    team2 = context["team2"]
    venue = context["venue"]
    toss_winner = context.get("toss_winner")
    toss_decision = context.get("toss_decision")
    
    if toss_winner and toss_decision:
        batting_first_team = (
            toss_winner if toss_decision == "bat" else (team2 if toss_winner == team1 else team1)
        )
    else:
        batting_first_team = team1 
    team1_score = predict_score(team1, venue, batting_first=batting_first_team, opponent=team2, matches_df=matches_df, date=date)
    team2_score = predict_score(team2, venue, batting_first=not batting_first_team, opponent=team1, matches_df=matches_df, date=date)
    return {
        "team1": team1_score,
        "team2": team2_score
    }

def generate_wickets_prediction(date, matches_df, deliveries_df):
    context = get_match_context(date)
    if context and 'team1' in context and 'team2' in context:
        team1 = context['team1']
        team2 = context['team2']
        venue = context.get('venue', 'Unknown')
        return {
            "match": {"teams": [team1, team2], "date": context.get('date', date)},
            "predictions": {
                team1: predict_wickets(team1, venue, team2, matches_df, deliveries_df),
                team2: predict_wickets(team2, venue, team1, matches_df, deliveries_df)
            }
        }
    
    live_matches = fetch_live_data(date)
    gmt_start, gmt_end = get_gmt_window(date)
    for match in live_matches:
        match_time = pytz.UTC.localize(datetime.strptime(match['dateTimeGMT'], "%Y-%m-%dT%H:%M:%S"))
        if (gmt_start <= match_time <= gmt_end and match['matchType'] == 't20' and
            any(team in match['teams'] for team in IPL_TEAMS)):
            team1, team2 = match['teams']
            venue = match.get('venue', 'Unknown')
            return {
                "match": {"teams": [team1, team2], "date": match['dateTimeGMT']},
                "predictions": {
                    team1: predict_wickets(team1, venue, team2, matches_df, deliveries_df),
                    team2: predict_wickets(team2, venue, team1, matches_df, deliveries_df)
                }
            }
    return {"error": f"No IPL match found on {date}"}

def generate_powerplay_prediction(date: str, matches_df, deliveries_df):
    context = get_match_context(date)
    if not context:
        return {"error": f"No context found for date {date}. Please update context first."}

    team1 = context["team1"]
    team2 = context["team2"]
    venue = context["venue"]

    return {
        team1: predict_power_play(team1, venue, matches_df, deliveries_df, date),
        team2: predict_power_play(team2, venue, matches_df, deliveries_df, date)
    }


def parse_query_with_gpt(query: str) -> list:
    system_prompt = (
        "You are a cricket assistant. Extract the INTENTS from a user question "
        "related to a live IPL match. Return a list of structured intents like: "
        "[{'intent': 'match_winner'}, {'intent': 'total_wickets'}]. "
        "Possible intents include: match_winner, toss_result, total_score, total_wickets, "
        "powerplay_performance, early_wicket, top3_batsman, boundaries, super_over_chance."
    )

    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": query}
            ],
            temperature=0.3
        )

        content = response.choices[0].message.content
        print("\n----- GPT RAW RESPONSE -----\n", content)

        match = re.search(r"\[.*\]", content, re.DOTALL)
        if match:
            parsed = eval(match.group(0))
            print("✅ Parsed GPT Intents:", parsed)
            return parsed
        else:
            print("❌ No list structure found in GPT response")
            return [{"intent": "fallback"}]

    except Exception as e:
        print("❌ GPT Parsing Error:", str(e))
        return [{"intent": "fallback"}]

def compare_teams(team1, team2, venue, matches_df, deliveries_df):
    stats1 = calculate_team_stats(team1, venue, matches_df, deliveries_df)
    stats2 = calculate_team_stats(team2, venue, matches_df, deliveries_df)

    return {
        team1: {
            "win_rate": round(stats1['win_rate'] * 100, 1),
            "average_score": round(stats1['avg_score'], 1),
            "average_wickets_lost": round(stats1['avg_wickets'], 1),
            "average_powerplay_runs": round(stats1['avg_pp_runs'], 1),
            "average_powerplay_wickets": round(stats1['avg_pp_wickets'], 1)
        },
        team2: {
            "win_rate": round(stats2['win_rate'] * 100, 1),
            "average_score": round(stats2['avg_score'], 1),
            "average_wickets_lost": round(stats2['avg_wickets'], 1),
            "average_powerplay_runs": round(stats2['avg_pp_runs'], 1),
            "average_powerplay_wickets": round(stats2['avg_pp_wickets'], 1)
        }
    }

def generate_recent_win_prediction(date, matches_df, deliveries_df):
    context = get_match_context(date)
    if not context:
        return {"error": "Match context not found"}

    team1 = context["team1"]
    team2 = context["team2"]
    venue = context["venue"]
    toss_winner = context.get("toss_winner")
    toss_decision = context.get("toss_decision")

    if toss_winner and toss_decision:
        return predict_winner_post_toss_recent(team1, team2, venue, toss_winner, toss_decision, recent_matches_df, deliveries_df)
    else:
        return predict_winner_pre_toss_recent(team1, team2, venue, recent_matches_df, deliveries_df)

def generate_recent_score_prediction(date, matches_df):
    context = get_match_context(date)
    if not context:
        return {"error": "Match context not found"}
    
    team1 = context["team1"]
    team2 = context["team2"]
    venue = context["venue"]
    toss_winner = context.get("toss_winner")
    toss_decision = context.get("toss_decision")

    if not toss_winner or not toss_decision:
        return {"error": "Toss info not available"}

    batting_first = toss_decision == "bat"
    return {
        team1: predict_score(team1, venue, batting_first=(toss_winner == team1 and batting_first), matches_df=recent_matches_df),
        team2: predict_score(team2, venue, batting_first=(toss_winner == team2 and batting_first), matches_df=recent_matches_df)
    }

def generate_recent_wickets_prediction(date, matches_df, deliveries_df):
    context = get_match_context(date)
    if not context:
        return {"error": "Match context not found"}

    team1 = context["team1"]
    team2 = context["team2"]
    venue = context["venue"]

    return {
        team1: predict_wickets(team1, venue, recent_matches_df, deliveries_df),
        team2: predict_wickets(team2, venue, recent_matches_df, deliveries_df)
    }

def generate_recent_powerplay_prediction(date, matches_df, deliveries_df):
    context = get_match_context(date)
    if not context:
        return {"error": "Match context not found"}

    team1 = context["team1"]
    team2 = context["team2"]
    venue = context["venue"]

    return {
        team1: predict_power_play(team1, venue, matches_df, deliveries_df, date),
        team2: predict_power_play(team2, venue, matches_df, deliveries_df, date)
    }

def predict_winner_pre_toss_recent(team1, team2, venue, matches_df, deliveries_df):
    return predict_winner_pre_toss(team1, team2, venue, matches_df, deliveries_df)

def predict_winner_post_toss_recent(team1, team2, venue, toss_winner, toss_decision, matches_df, deliveries_df):
    return predict_winner_post_toss(team1, team2, venue, toss_winner, toss_decision, matches_df, deliveries_df)