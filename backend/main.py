from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, List, Dict
from pydantic import BaseModel
from datetime import datetime, timedelta
import pytz
from backend.utils import get_gmt_window
from fastapi import APIRouter
from backend.prediction_engine import (
    load_schedule_if_available, get_today_match, compare_teams,
    match_contexts, get_venue_based_stats, get_head_to_head_summary,
    predict_early_wicket_probability, get_prediction_breakdown,
    get_team_stats_summary, get_pre_match_context_summary,
    get_full_match_context, predict_powerplay_performance,
    update_live_match_state, get_live_match_state, handle_nlp_query,
    parse_query_with_gpt, generate_win_prediction, generate_score_prediction,
    generate_wickets_prediction, generate_powerplay_prediction,
    load_ipl_data,update_match_context, get_match_context as get_match_context_by_date,
    predict_winner_post_toss, predict_winner_pre_toss, predict_score,
    predict_wickets, predict_power_play, generate_recent_win_prediction,
    generate_recent_score_prediction, generate_recent_wickets_prediction,
    generate_recent_powerplay_prediction, predict_winner_pre_toss_recent,
    predict_winner_post_toss_recent,live_match_state,normalize_team_name,calculate_team_stats,calculate_bowler_impact
)

from backend.live_data_provider import get_todays_match, get_match_details, fetch_live_data,IPL_TEAMS,get_match_by_date,get_first_innings_score,get_todays_matches



recent_matches_df, recent_deliveries_df = load_ipl_data()
recent_deliveries_df = recent_deliveries_df.merge(
    recent_matches_df[["id", "venue"]],
    left_on="match_id",
    right_on="id",
    how="left"
)

recent_router = APIRouter()
app = FastAPI(title="IPL Live Match Predictor", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Frontend origin
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods (GET, POST, etc.)
    allow_headers=["*"],  # Allow all headers
)

# Load data on startup
@app.on_event("startup")
def on_startup():
    load_schedule_if_available()

matches_df, deliveries_df = load_ipl_data()

class MatchContextRequest(BaseModel):
    date: str
    venue: str
    team1: str
    team2: str
    toss_winner: str
    toss_decision: str
    playing_11: Optional[Dict[str, List[str]]] = None

class LiveMatchStateRequest(BaseModel):
    date: str
    inning: Optional[int] = 1
    batting_team: Optional[str] = None
    runs: Optional[int] = 0
    wickets: Optional[int] = 0
    overs: Optional[float] = 0.0
    batsmen: Optional[List[str]] = []

@app.post("/update-match-context")
def update_match_context_endpoint(date: str = datetime.utcnow().strftime("%Y-%m-%d"), match_number: int = 0):
    matches = fetch_live_data(date)
    if not matches or match_number >= len(matches):
        raise HTTPException(status_code=404, detail=f"No IPL match #{match_number} found on {date}.")

    raw_match = matches[match_number]
    match_id = raw_match["matchId"]

    match_info = {
        "match_id": match_id,
        "team1": normalize_team_name(raw_match["team1"]["teamName"]),
        "team2": normalize_team_name(raw_match["team2"]["teamName"]),
        "venue": raw_match["venueInfo"]["ground"],
        "status": raw_match.get("status", "Preview"),
        "date": datetime.utcfromtimestamp(int(raw_match["startDate"]) / 1000).strftime("%a, %d %b %Y")
    }

    print(f"✔️ Normalized Teams: {match_info['team1']} vs {match_info['team2']}")
    print(f"📅 Match info fetched: {match_info}")

    match_details = get_match_details(match_id)
    if not match_details:
        raise HTTPException(status_code=500, detail="Could not fetch match details.")

    update_match_context(
        date=datetime.strptime(match_info["date"], "%a, %d %b %Y").strftime("%Y-%m-%d"),
        team1=match_info["team1"],
        team2=match_info["team2"],
        venue=match_info["venue"],
        status=match_info["status"],
        toss_winner=match_details["toss_winner"],
        toss_decision=match_details["toss_decision"],
        playing_11=match_details["playing_11"],
        squads=match_details["squads"]
    )
    innings = match_details.get("innings", [])
    print(f"🔍 Innings from match_details: {innings}")

    current_batting_team = None
    runs = wickets = overs = 0.0

    if innings:
        current_innings = max(innings, key=lambda x: x.get("inningsId", 0))
        current_batting_team = normalize_team_name(current_innings.get("batTeamName"))
        runs = current_innings.get("score", 0)
        wickets = current_innings.get("wickets", 0)
        overs = current_innings.get("overs", 0.0)
        first_innings_team = normalize_team_name(min(innings, key=lambda x: x.get("inningsId", 0)).get("batTeamName"))
    else:
        toss_winner = match_details.get("toss_winner")
        toss_decision = match_details.get("toss_decision")
        if toss_winner and toss_decision:
            toss_winner_normalized = normalize_team_name(toss_winner)
            if toss_decision == "bat":
                first_innings_team = toss_winner_normalized
            else:
                first_innings_team = match_info["team2"] if toss_winner_normalized == match_info["team1"] else match_info["team1"]
            current_batting_team = first_innings_team
            print(f"📌 Toss complete: {toss_winner} chose to {toss_decision}. {current_batting_team} will bat first.")
        else:
            current_batting_team = None
            first_innings_team = None
            runs = wickets = overs = 0

    # Fix powerplay data with normalization
    powerplay_data = match_details.get("powerplay", {})
    print(f"📊 Powerplay Data: {powerplay_data}")
    normalized_powerplay = {normalize_team_name(k): v for k, v in powerplay_data.items()}
    print(f"📊 Normalized Powerplay Data: {normalized_powerplay}")

    team1 = match_info["team1"]
    team2 = match_info["team2"]
    team1_pp_runs = normalized_powerplay.get(team1, {}).get("runs", 0)
    team1_pp_wickets = normalized_powerplay.get(team1, {}).get("wickets", 0)
    team2_pp_runs = normalized_powerplay.get(team2, {}).get("runs", 0)
    team2_pp_wickets = normalized_powerplay.get(team2, {}).get("wickets", 0)

    live_match_state[date] = {
        "batting_team": current_batting_team,
        "first_innings_team": first_innings_team,
        "runs": runs,
        "wickets": wickets,
        "overs": overs,
        f"{team1}_pp_runs": team1_pp_runs,
        f"{team1}_pp_wickets": team1_pp_wickets,
        f"{team2}_pp_runs": team2_pp_runs,
        f"{team2}_pp_wickets": team2_pp_wickets
    }
    print(f"✅ Updated live_match_state[{date}]: {live_match_state[date]}")

    return {
        "message": "Live match context updated successfully",
        "match": match_info,
        "playing_11": match_details["playing_11"]
    }

@app.get("/predict/winner")
def predict_winner(date: str):
    return generate_win_prediction(date, matches_df, deliveries_df)

@app.get("/predict/score")
def predict_score_range(date: str):
    return generate_score_prediction(date, matches_df)

@app.get("/predict/wickets")
def predict_wickets_range(date: str):
    return generate_wickets_prediction(date, matches_df, deliveries_df)

@app.get("/predict/powerplay")
def predict_powerplay_range(date: str):
    return generate_powerplay_prediction(date, matches_df, deliveries_df)

@app.get("/predict/winner-post-toss")
def get_post_toss_prediction(
    team1: Optional[str] = None,
    team2: Optional[str] = None,
    venue: Optional[str] = None,
    toss_winner: Optional[str] = None,
    toss_decision: Optional[str] = None,
    date: Optional[str] = None
):
    if date:
        context = get_match_context_by_date(date)
        if not context:
            return {"error": f"No match context found for date: {date}"}
        team1, team2 = context["teams"]
        venue = context["venue"]
        toss_winner = context["toss_winner"]
        toss_decision = context["toss_decision"]

    if not all([team1, team2, venue, toss_winner, toss_decision]):
        return {"error": "Missing required parameters."}

    return predict_winner_post_toss(team1, team2, venue, toss_winner, toss_decision, matches_df, deliveries_df)

@app.get("/predict/toss")
def simulate_toss(team1: str, team2: str):
    import random
    toss_winner = random.choice([team1, team2])
    toss_decision = random.choice(["bat", "field"])
    return {"toss_winner": toss_winner, "decision": toss_decision}

# main.py
@app.get("/match-context")
async def match_context(date: str):
    match = get_match_by_date(date)

    if not match:
        raise HTTPException(status_code=404, detail=f"No IPL match found on {date}")

    return {
        "match_id": match["match_id"],
        "teams": [match["team1"], match["team2"]],
        "venue": match["venue"],
        "date": match["date"],
        "status": match["status"]
    }

@app.post("/match-context")
async def set_match_context(teams: list[str], venue: str, toss_winner: str = None, toss_decision: str = None, date: str = None):
    """Set match context for predictions."""
    if not date:
        date = datetime.today().date().isoformat()
    update_match_context(date, toss_decision, venue, toss_winner, teams[0], teams[1])
    return {"message": "Match context updated", "teams": teams, "venue": venue}

@app.get("/match-context/summary")
def get_match_summary(team1: str, team2: str, venue: str):
    return get_pre_match_context_summary(team1, team2, venue, matches_df)

@app.get("/match-context/full")
def get_full_context(date: str):
    return get_full_match_context(date, matches_df, match_contexts)

@app.post("/update-live-match")
def update_live(state: LiveMatchStateRequest):
    update_live_match_state(state.date, state.dict(exclude_unset=True))
    return {"message": "Live match state updated", "date": state.date}

@app.get("/live-match-state")
def get_live(date: str):
    return get_live_match_state(date)

@app.get("/head-to-head")
def h2h(team1: str, team2: str):
    return get_head_to_head_summary(team1, team2, matches_df)

@app.get("/venue-head-to-head")
def venue_h2h(team1: str, team2: str, venue: str):
    return get_venue_based_stats(team1, team2, venue, matches_df)

@app.get("/predict/winner-breakdown")
def winner_breakdown(team1: str, team2: str, venue: str, toss_winner: str, toss_decision: str):
    return get_prediction_breakdown(team1, team2, venue, toss_winner, toss_decision, matches_df, deliveries_df)

@app.get("/compare-teams")
def compare(team1: str, team2: str, venue: str):
    return compare_teams(team1, team2, venue, matches_df, deliveries_df)

@app.get("/team-stats")
def team_stats(team: str, venue: str):
    return get_team_stats_summary(team, venue, matches_df, deliveries_df)

@app.get("/nlp-query/gpt")
def query_nlp(date: str, query: str):
    context = get_match_context_by_date(date)
    if not context:
        return [{"intent": "fallback", "result": f"No match context found for date {date}"}]
    parsed_intents = parse_query_with_gpt(query)
    results = []
    for item in parsed_intents:
        intent = item.get("intent")
        if intent == "match_winner":
            results.append({"intent": intent, "result": handle_nlp_query("who will win", date, matches_df, deliveries_df)})
        elif intent == "total_wickets":
            results.append({"intent": intent, "result": handle_nlp_query("how many wickets will fall", date, matches_df, deliveries_df)})
        elif intent == "powerplay_performance":
            results.append({"intent": intent, "result": handle_nlp_query("powerplay over 50", date, matches_df, deliveries_df)})
        elif intent == "super_over_chance":
            results.append({"intent": intent, "result": handle_nlp_query("super over", date, matches_df, deliveries_df)})
        elif intent == "early_wicket":
            result1 = predict_early_wicket_probability(context['teams'][0], deliveries_df, matches_df)
            result2 = predict_early_wicket_probability(context['teams'][1], deliveries_df, matches_df)
            results.append({"intent": "early_wicket", "result": [result1, result2]})
        else:
            results.append({"intent": intent, "result": "Unsupported intent"})
    return results

def get_average_run_rate_after(current_overs, current_wickets, team, opponent, venue, deliveries_df=recent_deliveries_df):
    # Filter for similar matches
    filtered = deliveries_df[
        (deliveries_df["batting_team"] == team) &
        (deliveries_df["bowling_team"] == opponent) &
        (deliveries_df["venue"] == venue)
    ]

    if filtered.empty:
        return 7.5  # fallback RR

    # Convert over + ball to ball number for filtering
    balls_so_far = int(current_overs * 6)
    
    grouped_innings = filtered.groupby(["match_id", "innings"])

    projected_rrs = []

    for _, group in grouped_innings:
        group = group.sort_values(by=["over", "ball"])
        group = group.reset_index(drop=True)

        # Get runs and balls after current state
        total_balls = len(group)
        if total_balls <= balls_so_far:
            continue  # skip if this innings is too short

        after_state = group.iloc[balls_so_far:]
        runs_after = after_state["total_runs"].sum()
        balls_remaining = len(after_state)

        if balls_remaining == 0:
            continue

        projected_rr = (runs_after / balls_remaining) * 6
        projected_rrs.append(projected_rr)

    if not projected_rrs:
        return 7.5

    return sum(projected_rrs) / len(projected_rrs)

def get_predicted_total_wickets(current_overs, current_wickets, team, opponent, venue, deliveries_df=recent_deliveries_df):
    filtered = deliveries_df[
        (deliveries_df["batting_team"] == team) &
        (deliveries_df["bowling_team"] == opponent) &
        (deliveries_df["venue"] == venue)
    ]

    if filtered.empty:
        return current_wickets + 3  # fallback: assume 3 more wickets may fall

    balls_so_far = int(current_overs * 6)
    
    grouped_innings = filtered.groupby(["match_id", "innings"])

    total_wicket_projections = []

    for _, group in grouped_innings:
        group = group.sort_values(by=["over", "ball"]).reset_index(drop=True)
        total_balls = len(group)

        if total_balls <= balls_so_far:
            continue  # skip short innings

        # Wickets before current state
        before_wickets = group.iloc[:balls_so_far]["isWicketDelivery"].sum()
        after_wickets = group.iloc[balls_so_far:]["isWicketDelivery"].sum()
        projected_total = before_wickets + after_wickets
        total_wicket_projections.append(projected_total)

    if not total_wicket_projections:
        return current_wickets + 3  # fallback

    return sum(total_wicket_projections) / len(total_wicket_projections)


@app.get("/predict/winner-live")
def predict_winner_live(date: str):
    context = get_match_context_by_date(date)
    if not context:
        return {"error": f"No context found for date {date}. Please update context first."}
    
    if "won by" in context.get("status", "").lower() or "match_abandoned" in context.get("status", "").lower():
        return {
            "message": "🏁 Match is completed. We’ll provide predictions tomorrow once the game starts."
        }

    team1 = normalize_team_name(context["team1"])
    team2 = normalize_team_name(context["team2"])
    venue = context.get("venue")
    live_state = get_live_match_state(date)

    current_batting_team = normalize_team_name(live_state.get("batting_team", ""))
    runs = live_state.get("runs", 0)
    overs = live_state.get("overs", 0)
    wickets = live_state.get("wickets", 0)

    if not current_batting_team or current_batting_team not in [team1, team2]:
        return {"error": "Live match state is incomplete or batting team doesn't match context."}

    first_innings_team = normalize_team_name(live_state.get("first_innings_team", ""))
    is_chasing = current_batting_team != first_innings_team
    current_score = runs
    balls_faced = overs * 6
    balls_remaining = 120 - balls_faced
    required_run_rate = None
    predicted_total = None
    target_score = None

    score_pred_1 = predict_score(team1, venue, batting_first=True, date=date)
    score_pred_2 = predict_score(team2, venue, batting_first=True, date=date)

    def extract_average_score(pred_str):
        numbers = [int(s) for s in pred_str.split() if s.isdigit()]
        return sum(numbers) / len(numbers) if len(numbers) == 2 else 170

    if is_chasing:
        target_score = live_state.get("target_score") or get_first_innings_score(date) + 1
        if current_score >= target_score:
            win_prob_batting = 95
        elif balls_remaining <= 0:
            win_prob_batting = 5
        else:
            required_run_rate = (target_score - current_score) / (balls_remaining / 6) if balls_remaining > 0 else None
            current_rr = current_score / overs if overs > 0 else 0
            run_rate_factor = min(40, max(-40, (current_rr - required_run_rate) * 10)) if required_run_rate else 0
            wicket_factor = (10 - wickets) / 10
            wicket_adjustment = (wicket_factor - 0.5) * 40
            balls_factor = (balls_remaining / 120) * 20
            win_prob_batting = 50 + run_rate_factor + wicket_adjustment + balls_factor
            win_prob_batting = max(5, min(95, win_prob_batting))
    else:
        predicted_total = extract_average_score(score_pred_1 if current_batting_team == team1 else score_pred_2)
        current_rr = current_score / overs if overs > 0 else 0
        expected_rr = 8.5
        run_rate_factor = min(30, max(-30, (current_rr - expected_rr) * 5))
        wicket_factor = (10 - wickets) / 10
        wicket_adjustment = (wicket_factor - 0.5) * 40
        balls_factor = ((120 - balls_faced) / 120) * 20
        win_prob_batting = 50 + run_rate_factor + wicket_adjustment + balls_factor
        win_prob_batting = max(5, min(95, win_prob_batting))

    batting_team = current_batting_team
    bowling_team = team2 if batting_team == team1 else team1

    # ✅ Always assign probability like this for clarity
    win_probs = {
        batting_team: round(win_prob_batting),
        bowling_team: round(100 - win_prob_batting)
    }

    response = {
        "live_prediction": f"{batting_team.title()} vs {bowling_team.title()}",
        "current_score": current_score,
        "overs": overs,
        "wickets": wickets,
        "win_probability": win_probs
    }

    if is_chasing:
        response["target_score"] = int(target_score)
        response["required_run_rate"] = round(required_run_rate, 2) if required_run_rate is not None else None

    return response


@app.get("/predict/score-live")
def predict_score_live(date: str):
    context = get_match_context_by_date(date)
    live_state = get_live_match_state(date)

    if not context or not live_state:
        return {"error": "Context or live state not found. Please update match context first."}
    
    if "won by" in context.get("status", "").lower() or "match abandoned" in context.get("status", "").lower():
        return {
            "message": "🏁 Match is completed. We’ll provide predictions tomorrow once the game starts."
        }

    batting_team = live_state.get("batting_team")
    venue = context["venue"]
    opponent = context["team1"] if batting_team == context["team2"] else context["team2"]

    current_runs = live_state.get("runs", 0)
    current_overs = live_state.get("overs", 0.0)
    current_wickets = live_state.get("wickets", 0)

    first_innings_team = live_state.get("first_innings_team")
    is_chasing = batting_team != first_innings_team
    current_rr = current_runs / current_overs if current_overs > 0 else 0

    response = {
        "match_date": date,
        "venue": venue,
        "batting_team": batting_team,
        "current_score": current_runs,
        "overs": round(current_overs, 1),
        "wickets": current_wickets,
    }

    if round(current_overs, 1) >= 19.6:
        response["projected_final_score"] = current_runs
        response["insight"] = "🛑 Innings complete. Final score recorded."
    elif not is_chasing:
        overs_remaining = 20 - current_overs
        historical_rr = get_average_run_rate_after(current_overs, current_wickets, batting_team, opponent, venue)
        projected_final_score = current_runs + (historical_rr * overs_remaining)
        response["projected_final_score"] = int(projected_final_score)
        response["insight"] = f"📊 Projected score: {int(projected_final_score)} based on historical scoring after this phase."
    else:
        target = get_first_innings_score(date) + 1
        balls_faced = current_overs * 6
        balls_remaining = max(0, 120 - balls_faced)

        if current_rr > 0:
            required_overs = (target - current_runs) / current_rr
        else:
            required_overs = float("inf")

        if current_runs >= target:
            insight = f"🎯 {batting_team.title()} has already chased down the target of {target}."
        elif required_overs <= (balls_remaining / 6):
            insight = f"🟢 At current RR ({current_rr:.2f}), {batting_team.title()} can chase {target} in about {required_overs:.1f} overs."
        else:
            projected_score = int(current_rr * (balls_remaining / 6) + current_runs)
            insight = f"🔴 At current RR ({current_rr:.2f}), {batting_team.title()} may fall short. Projected score: {projected_score}"

        response["target_score"] = target
        response["run_rate"] = round(current_rr, 2)
        response["insight"] = insight

    return response




@app.get("/predict/wickets-live")
def predict_wickets_live(date: str):
    context = get_match_context_by_date(date)
    live_state = get_live_match_state(date)

    if not context or not live_state:
        return {"error": "Context or live state not found. Please update match context first."}
    
    if "won by" in context.get("status", "").lower() or "match abandoned" in context.get("status", "").lower():
        return {
            "message": "🏁 Match is completed. We’ll provide predictions tomorrow once the game starts."
        }

    batting_team = live_state.get("batting_team")
    venue = context["venue"]
    opponent = context["team1"] if batting_team == context["team2"] else context["team2"]

    current_wickets = live_state.get("wickets", 0)
    current_overs = live_state.get("overs", 0.0)

    # ✅ Check if innings is over (19.6 or more)
    if round(current_overs, 1) >= 19.6:
        projected_total_wickets = current_wickets
    else:
        projected_total_wickets = get_predicted_total_wickets(current_overs, current_wickets, batting_team, opponent, venue)
        projected_total_wickets = min(10, projected_total_wickets)  # ✅ cap at 10

    return {
        "match_date": date,
        "venue": venue,
        "batting_team": batting_team,
        "overs": round(current_overs, 1),
        "current_wickets": current_wickets,
        "projected_total_wickets": int(projected_total_wickets)
    }


@app.get("/predict/powerplay-live")
def predict_powerplay_live(date: str):
    context = get_match_context_by_date(date)
    live_state = get_live_match_state(date)

    if not context or not live_state:
        return {"error": "Context or live state not found. Please update match context first."}

    # If match already completed
    if "won by" in context.get("status", "").lower() or "match abandoned" in context.get("status", "").lower():
        return {
            "message": "🏁 Match is completed. We’ll provide predictions tomorrow once the game starts."
        }

    batting_team = live_state.get("batting_team")
    first_innings_team = live_state.get("first_innings_team")
    if not batting_team:
        return {
            "message": "📢 Match hasn’t started yet — powerplay prediction will be available once the toss and innings begin."
        }
    venue = context.get("venue", "Unknown")
    overs = live_state.get("overs", 0.0)
    current_runs = live_state.get("runs", 0)
    current_wickets = live_state.get("wickets", 0)

    if overs > 6:
        return {
            "message": "🚫 Powerplay is complete. Live prediction only available during the first 6 overs."
        }

    opponent = context["team1"] if batting_team == context["team2"] else context["team2"]
    innings = "first" if batting_team == first_innings_team else "second"

    # Get historical PP stats
    team_stats = calculate_team_stats(batting_team, venue, recent_matches_df, recent_deliveries_df)
    avg_pp_runs = team_stats.get("avg_pp_runs", 45)
    avg_pp_wickets = team_stats.get("avg_pp_wickets", 2)

    # Get opponent bowling strength
    bowler_impact = calculate_bowler_impact(opponent, venue, recent_deliveries_df, recent_matches_df)
    runs_adj = 1 - (bowler_impact * 0.03)
    wkts_adj = bowler_impact * 0.25

    # Remaining overs in PP
    remaining_overs = 6 - overs
    runs_per_over = (avg_pp_runs * runs_adj) / 6
    wkts_per_over = (avg_pp_wickets + wkts_adj) / 6

    predicted_pp_runs = current_runs + (runs_per_over * remaining_overs)
    predicted_pp_wkts = current_wickets + (wkts_per_over * remaining_overs)

    predicted_pp_runs = int(round(predicted_pp_runs))
    predicted_pp_wkts = int(round(predicted_pp_wkts))

    return {
        "match_date": date,
        "venue": venue,
        "batting_team": batting_team,
        "opponent": opponent,
        "innings": innings,
        "overs": round(overs, 1),
        "current_pp_runs": current_runs,
        "current_pp_wickets": current_wickets,
        "predicted_pp_total": {
            "runs": f"{predicted_pp_runs - 5}-{predicted_pp_runs + 5}",
            "wickets": f"{max(0, predicted_pp_wkts - 1)}-{min(6, predicted_pp_wkts + 1)}"
        }
    }

@app.get("/matches")
def list_matches(date: str):
    matches = get_todays_matches(date)
    return {
        "matches": [
            {
                "match_number": i,
                "match_id": match.get("matchId"),
                "teams": [match["team1"]["teamName"], match["team2"]["teamName"]],
                "venue": match["venueInfo"]["ground"],
                "start_time": datetime.utcfromtimestamp(int(match["startDate"]) / 1000).isoformat()
            } for i, match in enumerate(matches)
        ]
    }



app.include_router(recent_router)