from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from datetime import datetime
import hashlib
import json
import os
import uuid
import logging
import contextvars

from backend.prediction_engine_api import pre_match_predictions, live_predictions, MatchNotFound
from backend.live_data_provider import (
    fetch_live_data_for_series,
    get_match_details,
    T20WC_SERIES_ID,
    UpstreamError,
)
from backend.cache import cache
from backend.config import PRED_PRE_TOSS_TTL, PRED_POST_TOSS_TTL, PRED_COMPLETED_TTL, PRED_IN_PROGRESS_TTL

correlation_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("correlation_id", default="-")

logger = logging.getLogger(__name__)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        cid = request.headers.get("x-correlation-id", str(uuid.uuid4()))
        correlation_id_var.set(cid)
        logger.info(">> %s %s", request.method, request.url.path)
        response = await call_next(request)
        response.headers["x-correlation-id"] = cid
        return response


IPL_SERIES_ID = int(os.getenv("IPL_SERIES_ID", "9237"))

app = FastAPI(title="Cricket Prediction API", version="2.0")

app.add_middleware(CorrelationIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["ETag"],
)


def _etag_response(request: Request, data: dict):
    """Return JSONResponse with ETag, or 304 if client already has current version."""
    body = json.dumps(data, sort_keys=True)
    etag = hashlib.md5(body.encode()).hexdigest()
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304)
    return JSONResponse(content=data, headers={"ETag": etag})


_PRED_STAGE_TTL = {
    "pre_toss": PRED_PRE_TOSS_TTL,
    "post_toss": PRED_POST_TOSS_TTL,
    "completed": PRED_COMPLETED_TTL,
    "in_progress": PRED_IN_PROGRESS_TTL,
}


def _safe_pre_match(series_id: int, date: str, match_number: int = 0):
    if match_number < 0:
        raise HTTPException(status_code=422, detail="match_number must be >= 0")
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="date must be YYYY-MM-DD") from exc

    pred_cache_key = f"pred:pre:{series_id}:{date}:{match_number}:v1"
    cached = cache.get(pred_cache_key)
    if cached is not None:
        cached["_cached"] = True
        return cached

    try:
        result = pre_match_predictions(series_id=series_id, date=date, match_number=match_number)
    except MatchNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except UpstreamError as exc:
        raise HTTPException(status_code=503, detail="Upstream Cricbuzz API unavailable") from exc

    stage = result.get("prediction_stage", "pre_toss")
    ttl = _PRED_STAGE_TTL.get(stage, PRED_PRE_TOSS_TTL)
    cache.set(pred_cache_key, result, ttl)
    return result


def _safe_live(series_id: int, date: str, match_number: int = 0):
    if match_number < 0:
        raise HTTPException(status_code=422, detail="match_number must be >= 0")
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="date must be YYYY-MM-DD") from exc
    try:
        return live_predictions(series_id=series_id, date=date, match_number=match_number)
    except MatchNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except UpstreamError as exc:
        raise HTTPException(status_code=503, detail="Upstream Cricbuzz API unavailable") from exc


def _match_info_from_series(series_id: int, date: str, match_number: int):
    matches = fetch_live_data_for_series(date, series_id)
    if not matches or match_number >= len(matches):
        return None
    raw_match = matches[match_number]
    return {
        "match_id": raw_match.get("matchId"),
        "team1": raw_match["team1"]["teamName"],
        "team2": raw_match["team2"]["teamName"],
        "venue": raw_match["venueInfo"]["ground"],
        "status": raw_match.get("status", "Preview"),
        "date": datetime.utcfromtimestamp(int(raw_match["startDate"]) / 1000).strftime("%a, %d %b %Y"),
    }


@app.post("/update-match-context")
def update_match_context_endpoint(date: str = datetime.utcnow().strftime("%Y-%m-%d"), match_number: int = 0):
    if match_number < 0:
        raise HTTPException(status_code=422, detail="match_number must be >= 0")
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="date must be YYYY-MM-DD") from exc

    try:
        match_info = _match_info_from_series(IPL_SERIES_ID, date, match_number)
    except UpstreamError as exc:
        raise HTTPException(status_code=503, detail="Upstream Cricbuzz API unavailable") from exc
    if not match_info:
        raise HTTPException(status_code=404, detail=f"No IPL match #{match_number} found on {date}.")

    match_details = get_match_details(match_info["match_id"]) if match_info.get("match_id") else None
    return {
        "message": "Match context updated successfully",
        "match": match_info,
        "playing_11": match_details.get("playing_11") if match_details else {},
    }


@app.post("/t20wc/update-match-context")
def update_t20wc_match_context(date: str = datetime.utcnow().strftime("%Y-%m-%d"), match_number: int = 0):
    if not T20WC_SERIES_ID:
        raise HTTPException(status_code=500, detail="T20WC_SERIES_ID is not configured.")
    if match_number < 0:
        raise HTTPException(status_code=422, detail="match_number must be >= 0")
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="date must be YYYY-MM-DD") from exc

    try:
        match_info = _match_info_from_series(T20WC_SERIES_ID, date, match_number)
    except UpstreamError as exc:
        raise HTTPException(status_code=503, detail="Upstream Cricbuzz API unavailable") from exc
    if not match_info:
        raise HTTPException(status_code=404, detail=f"No T20 World Cup match #{match_number} found on {date}.")

    match_details = get_match_details(match_info["match_id"]) if match_info.get("match_id") else None
    return {
        "message": "T20 World Cup match context updated successfully",
        "match": match_info,
        "playing_11": match_details.get("playing_11") if match_details else {},
    }


@app.get("/matches")
def list_matches(request: Request, date: str):
    try:
        matches = fetch_live_data_for_series(date, IPL_SERIES_ID)
    except UpstreamError as exc:
        raise HTTPException(status_code=503, detail="Upstream Cricbuzz API unavailable") from exc
    data = {
        "matches": [
            {
                "match_number": i,
                "match_id": match.get("matchId"),
                "teams": [match["team1"]["teamName"], match["team2"]["teamName"]],
                "venue": match["venueInfo"]["ground"],
                "start_time": datetime.utcfromtimestamp(int(match["startDate"]) / 1000).isoformat(),
            }
            for i, match in enumerate(matches)
        ]
    }
    return _etag_response(request, data)


@app.get("/t20wc/matches")
def list_t20wc_matches(request: Request, date: str):
    if not T20WC_SERIES_ID:
        raise HTTPException(status_code=500, detail="T20WC_SERIES_ID is not configured.")
    try:
        matches = fetch_live_data_for_series(date, T20WC_SERIES_ID)
    except UpstreamError as exc:
        raise HTTPException(status_code=503, detail="Upstream Cricbuzz API unavailable") from exc
    data = {
        "matches": [
            {
                "match_number": i,
                "match_id": match.get("matchId"),
                "teams": [match["team1"]["teamName"], match["team2"]["teamName"]],
                "venue": match["venueInfo"]["ground"],
                "start_time": datetime.utcfromtimestamp(int(match["startDate"]) / 1000).isoformat(),
            }
            for i, match in enumerate(matches)
        ]
    }
    return _etag_response(request, data)


@app.get("/predict/pre-match")
def predict_pre_match(series_id: int, date: str, match_number: int = 0):
    return _safe_pre_match(series_id=series_id, date=date, match_number=match_number)


@app.get("/predict/live")
def predict_live(series_id: int, date: str, match_number: int = 0):
    return _safe_live(series_id=series_id, date=date, match_number=match_number)


@app.get("/predict/winner")
def predict_winner(date: str, match_number: int = 0):
    payload = _safe_pre_match(series_id=IPL_SERIES_ID, date=date, match_number=match_number)
    payload["deprecated"] = True
    payload["use"] = "/predict/pre-match"
    return payload


@app.get("/predict/score")
def predict_score_range(date: str, match_number: int = 0):
    payload = _safe_pre_match(series_id=IPL_SERIES_ID, date=date, match_number=match_number)
    payload["deprecated"] = True
    payload["use"] = "/predict/pre-match"
    return payload


@app.get("/predict/wickets")
def predict_wickets_range(date: str, match_number: int = 0):
    payload = _safe_pre_match(series_id=IPL_SERIES_ID, date=date, match_number=match_number)
    payload["deprecated"] = True
    payload["use"] = "/predict/pre-match"
    return payload


@app.get("/predict/powerplay")
def predict_powerplay_range(date: str, match_number: int = 0):
    payload = _safe_pre_match(series_id=IPL_SERIES_ID, date=date, match_number=match_number)
    payload["deprecated"] = True
    payload["use"] = "/predict/pre-match"
    return payload


@app.get("/t20wc/predict/winner")
def predict_t20wc_winner(date: str, match_number: int = 0):
    if not T20WC_SERIES_ID:
        raise HTTPException(status_code=500, detail="T20WC_SERIES_ID is not configured.")
    payload = _safe_pre_match(series_id=T20WC_SERIES_ID, date=date, match_number=match_number)
    payload["deprecated"] = True
    payload["use"] = "/predict/pre-match"
    return payload


@app.get("/t20wc/predict/score")
def predict_t20wc_score(date: str, match_number: int = 0):
    if not T20WC_SERIES_ID:
        raise HTTPException(status_code=500, detail="T20WC_SERIES_ID is not configured.")
    payload = _safe_pre_match(series_id=T20WC_SERIES_ID, date=date, match_number=match_number)
    payload["deprecated"] = True
    payload["use"] = "/predict/pre-match"
    return payload


@app.get("/t20wc/predict/wickets")
def predict_t20wc_wickets(date: str, match_number: int = 0):
    if not T20WC_SERIES_ID:
        raise HTTPException(status_code=500, detail="T20WC_SERIES_ID is not configured.")
    payload = _safe_pre_match(series_id=T20WC_SERIES_ID, date=date, match_number=match_number)
    payload["deprecated"] = True
    payload["use"] = "/predict/pre-match"
    return payload


@app.get("/t20wc/predict/powerplay")
def predict_t20wc_powerplay(date: str, match_number: int = 0):
    if not T20WC_SERIES_ID:
        raise HTTPException(status_code=500, detail="T20WC_SERIES_ID is not configured.")
    payload = _safe_pre_match(series_id=T20WC_SERIES_ID, date=date, match_number=match_number)
    payload["deprecated"] = True
    payload["use"] = "/predict/pre-match"
    return payload


@app.get("/t20wc/predict/live")
def predict_t20wc_live(date: str, match_number: int = 0):
    if not T20WC_SERIES_ID:
        raise HTTPException(status_code=500, detail="T20WC_SERIES_ID is not configured.")
    payload = _safe_live(series_id=T20WC_SERIES_ID, date=date, match_number=match_number)
    payload["deprecated"] = True
    payload["use"] = "/predict/live"
    return payload
