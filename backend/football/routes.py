"""Football API routes.

Mounted at ``/api/football`` by main.py.
"""

from __future__ import annotations

from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException

from backend.football.constants import BASE_URL, WC_LEAGUE_ID, WC_SEASON
from backend.football.data_provider import APIFootballClient
from backend.football.deps import get_football_client
from backend.football.exceptions import (
    APIFootballError,
    PlanLimitationError,
    QuotaExhaustedError,
    RateLimitError,
    UpstreamError,
)
from backend.football.schemas import CoverageStatus

router = APIRouter()


# ── Error translation ─────────────────────────────────────────────────


def _raise_for_football_error(exc: APIFootballError) -> NoReturn:
    """Convert a football exception into the appropriate HTTPException."""
    if isinstance(exc, (RateLimitError, QuotaExhaustedError)):
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    if isinstance(exc, PlanLimitationError):
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if isinstance(exc, UpstreamError):
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    # ParseError, generic APIFootballError
    raise HTTPException(status_code=502, detail=str(exc)) from exc


# ── Endpoints ─────────────────────────────────────────────────────────


@router.get("/health")
async def health() -> dict:
    """Health check — no upstream call, no auth required."""
    return {
        "status": "ok",
        "provider": "api-football",
        "base_url": BASE_URL,
    }


@router.get("/fixtures")
async def list_fixtures(
    league: int = WC_LEAGUE_ID,
    season: int = WC_SEASON,
    client: APIFootballClient = Depends(get_football_client),
) -> dict:
    """List all fixtures for a league/season."""
    try:
        fixtures = await client.get_fixtures(league=league, season=season)
    except APIFootballError as exc:
        _raise_for_football_error(exc)

    return {
        "count": len(fixtures),
        "fixtures": [fx.model_dump(mode="json") for fx in fixtures],
    }


@router.get("/fixtures/{fixture_id}")
async def get_fixture(
    fixture_id: int,
    client: APIFootballClient = Depends(get_football_client),
) -> dict:
    """Single fixture by ID."""
    try:
        fixture = await client.get_fixture(fixture_id)
    except APIFootballError as exc:
        _raise_for_football_error(exc)

    if fixture is None:
        raise HTTPException(
            status_code=404, detail=f"Fixture {fixture_id} not found"
        )
    return fixture.model_dump(mode="json")


@router.get("/coverage")
async def get_coverage(
    client: APIFootballClient = Depends(get_football_client),
) -> dict:
    """Coverage flags for WC 2026 with gap warnings."""
    try:
        cov = await client.get_coverage()
    except APIFootballError as exc:
        _raise_for_football_error(exc)

    if cov is None:
        raise HTTPException(
            status_code=404, detail="Coverage data not available"
        )
    status = CoverageStatus.from_af_coverage(cov)
    return status.model_dump()
