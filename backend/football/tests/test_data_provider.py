"""Tests for APIFootballClient using respx to mock httpx."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest
import respx

from backend.cache import CacheClient
from backend.football.constants import (
    BASE_URL,
    HEADER_RATE_LIMIT_MINUTE_REMAINING,
    HEADER_REQUESTS_REMAINING,
    STALE_TTL_MULTIPLIER,
)
from backend.football.data_provider import APIFootballClient
from backend.football.exceptions import (
    APIFootballError,
    PlanLimitationError,
    QuotaExhaustedError,
    RateLimitError,
    UpstreamError,
)
from backend.shared.async_singleflight import AsyncSingleflight

# ── Helpers ───────────────────────────────────────────────────────────

_FIXTURE_ITEM: dict[str, Any] = {
    "fixture": {
        "id": 100,
        "referee": None,
        "timezone": "UTC",
        "date": "2026-06-11T18:00:00+00:00",
        "timestamp": 1781366400,
        "venue": {"id": 1, "name": "Stadium", "city": "City"},
        "status": {"long": "Not Started", "short": "NS", "elapsed": None},
    },
    "league": {
        "id": 1,
        "name": "World Cup",
        "country": "World",
        "season": 2026,
        "round": "Group A - 1",
    },
    "teams": {
        "home": {"id": 10, "name": "TeamA", "logo": "a.png", "winner": None},
        "away": {"id": 20, "name": "TeamB", "logo": "b.png", "winner": None},
    },
    "goals": {"home": None, "away": None},
    "score": {
        "halftime": {"home": None, "away": None},
        "fulltime": {"home": None, "away": None},
        "extratime": {"home": None, "away": None},
        "penalty": {"home": None, "away": None},
    },
}

_RATE_LIMIT_HEADERS = {
    HEADER_REQUESTS_REMAINING: "99",
    HEADER_RATE_LIMIT_MINUTE_REMAINING: "9",
}


def _wrap(items: list[dict], errors: Any = []) -> dict:  # noqa: B006
    """Build a standard API-Football envelope."""
    return {
        "get": "fixtures",
        "parameters": {},
        "errors": errors,
        "results": len(items),
        "paging": {"current": 1, "total": 1},
        "response": items,
    }


def _fresh_client() -> tuple[APIFootballClient, CacheClient, AsyncSingleflight]:
    cache = CacheClient()
    sf = AsyncSingleflight()
    client = APIFootballClient("test-key", cache, sf)
    return client, cache, sf


# ── Tests ─────────────────────────────────────────────────────────────


@respx.mock
async def test_get_fixtures_parses_response() -> None:
    """Successful /fixtures call returns list[AFFixture]."""
    respx.get(f"{BASE_URL}/fixtures").mock(
        return_value=httpx.Response(200, json=_wrap([_FIXTURE_ITEM]), headers=_RATE_LIMIT_HEADERS),
    )
    client, *_ = _fresh_client()
    async with client:
        fixtures = await client.get_fixtures()

    assert len(fixtures) == 1
    assert fixtures[0].fixture.id == 100
    assert fixtures[0].teams.home.name == "TeamA"


@respx.mock
async def test_get_fixture_empty_returns_none() -> None:
    """get_fixture returns None when results=0."""
    respx.get(f"{BASE_URL}/fixtures").mock(
        return_value=httpx.Response(200, json=_wrap([]), headers=_RATE_LIMIT_HEADERS),
    )
    client, *_ = _fresh_client()
    async with client:
        result = await client.get_fixture(999)

    assert result is None


@respx.mock
async def test_cache_hit_skips_upstream() -> None:
    """Second call for same params returns cached data, no HTTP call."""
    route = respx.get(f"{BASE_URL}/fixtures").mock(
        return_value=httpx.Response(200, json=_wrap([_FIXTURE_ITEM]), headers=_RATE_LIMIT_HEADERS),
    )
    client, *_ = _fresh_client()
    async with client:
        first = await client.get_fixtures()
        second = await client.get_fixtures()

    assert len(first) == 1
    assert len(second) == 1
    assert route.call_count == 1


@respx.mock
async def test_concurrent_calls_dedupe_via_singleflight() -> None:
    """Five concurrent calls for same key → one upstream call."""
    route = respx.get(f"{BASE_URL}/fixtures").mock(
        return_value=httpx.Response(200, json=_wrap([_FIXTURE_ITEM]), headers=_RATE_LIMIT_HEADERS),
    )
    client, *_ = _fresh_client()
    async with client:
        results = await asyncio.gather(
            *[client.get_fixtures() for _ in range(5)]
        )

    assert all(len(r) == 1 for r in results)
    assert route.call_count == 1


async def test_quota_exhausted_fails_fast() -> None:
    """When daily_remaining=0, raises immediately with no HTTP call."""
    client, *_ = _fresh_client()
    client._daily_remaining = 0

    async with client:
        with pytest.raises(QuotaExhaustedError):
            await client.get_fixtures()


@respx.mock
async def test_stale_fallback_on_5xx() -> None:
    """503 returns stale cached data when available."""
    client, cache, sf = _fresh_client()

    # Pre-populate stale cache
    key = APIFootballClient._cache_key("fixtures", {"league": 1, "season": 2026})
    stale_key = APIFootballClient._stale_key(key)
    cache.set(stale_key, [_FIXTURE_ITEM], 9999)

    respx.get(f"{BASE_URL}/fixtures").mock(
        return_value=httpx.Response(503, headers=_RATE_LIMIT_HEADERS),
    )
    async with client:
        result = await client.get_fixtures()

    assert len(result) == 1
    assert result[0].fixture.id == 100


@respx.mock
async def test_no_stale_fallback_on_4xx() -> None:
    """404 raises UpstreamError even if stale cache exists."""
    client, cache, sf = _fresh_client()

    key = APIFootballClient._cache_key("fixture", {"id": 999})
    stale_key = APIFootballClient._stale_key(key)
    cache.set(stale_key, [_FIXTURE_ITEM], 9999)

    respx.get(f"{BASE_URL}/fixtures").mock(
        return_value=httpx.Response(404, text="Not found", headers=_RATE_LIMIT_HEADERS),
    )
    async with client:
        with pytest.raises(UpstreamError) as exc_info:
            await client.get_fixture(999)
        assert exc_info.value.status_code == 404


@respx.mock
async def test_stale_fallback_disabled_for_events() -> None:
    """get_events passes stale_fallback=False — 503 raises, no fallback."""
    client, cache, sf = _fresh_client()

    key = APIFootballClient._cache_key("events", {"fixture": 100})
    stale_key = APIFootballClient._stale_key(key)
    cache.set(stale_key, [{"type": "Goal"}], 9999)

    respx.get(f"{BASE_URL}/fixtures/events").mock(
        return_value=httpx.Response(503, headers=_RATE_LIMIT_HEADERS),
    )
    async with client:
        with pytest.raises(UpstreamError):
            await client.get_events(100)


@respx.mock
async def test_errors_dict_with_plan_raises_plan_limitation() -> None:
    """API returns errors: {"Plan": "..."} → PlanLimitationError."""
    respx.get(f"{BASE_URL}/fixtures").mock(
        return_value=httpx.Response(
            200,
            json=_wrap([], errors={"Plan": "This endpoint requires a Pro plan"}),
            headers=_RATE_LIMIT_HEADERS,
        ),
    )
    client, *_ = _fresh_client()
    async with client:
        with pytest.raises(PlanLimitationError):
            await client.get_fixtures()


@respx.mock
async def test_errors_dict_with_ratelimit_raises_rate_limit() -> None:
    """API returns errors: {"rateLimit": "..."} → RateLimitError."""
    respx.get(f"{BASE_URL}/fixtures").mock(
        return_value=httpx.Response(
            200,
            json=_wrap([], errors={"rateLimit": "Too many requests"}),
            headers=_RATE_LIMIT_HEADERS,
        ),
    )
    client, *_ = _fresh_client()
    async with client:
        with pytest.raises(RateLimitError):
            await client.get_fixtures()


@respx.mock
async def test_errors_list_raises_api_football_error() -> None:
    """API returns errors as a non-empty list → APIFootballError."""
    respx.get(f"{BASE_URL}/fixtures").mock(
        return_value=httpx.Response(
            200,
            json=_wrap([], errors=["Something went wrong"]),
            headers=_RATE_LIMIT_HEADERS,
        ),
    )
    client, *_ = _fresh_client()
    async with client:
        with pytest.raises(APIFootballError, match="Something went wrong"):
            await client.get_fixtures()


@respx.mock
async def test_timeout_with_stale_fallback() -> None:
    """httpx.TimeoutException falls back to stale cache."""
    client, cache, sf = _fresh_client()

    key = APIFootballClient._cache_key("fixtures", {"league": 1, "season": 2026})
    stale_key = APIFootballClient._stale_key(key)
    cache.set(stale_key, [_FIXTURE_ITEM], 9999)

    respx.get(f"{BASE_URL}/fixtures").mock(side_effect=httpx.ReadTimeout("timed out"))
    async with client:
        result = await client.get_fixtures()

    assert len(result) == 1


@respx.mock
async def test_timeout_without_stale_raises() -> None:
    """httpx.TimeoutException with no stale cache raises UpstreamError."""
    respx.get(f"{BASE_URL}/fixtures").mock(side_effect=httpx.ReadTimeout("timed out"))
    client, *_ = _fresh_client()
    async with client:
        with pytest.raises(UpstreamError):
            await client.get_fixtures()


@respx.mock
async def test_stale_key_written_on_success() -> None:
    """Successful response writes both fresh and stale cache keys."""
    respx.get(f"{BASE_URL}/fixtures").mock(
        return_value=httpx.Response(200, json=_wrap([_FIXTURE_ITEM]), headers=_RATE_LIMIT_HEADERS),
    )
    client, cache, sf = _fresh_client()
    async with client:
        await client.get_fixtures()

    key = APIFootballClient._cache_key("fixtures", {"league": 1, "season": 2026})
    stale_key = APIFootballClient._stale_key(key)
    assert cache.get(key) is not None
    assert cache.get(stale_key) is not None


@respx.mock
async def test_rate_limit_headers_update_state() -> None:
    """Response headers update daily_remaining and minute_remaining."""
    respx.get(f"{BASE_URL}/fixtures").mock(
        return_value=httpx.Response(
            200,
            json=_wrap([_FIXTURE_ITEM]),
            headers={HEADER_REQUESTS_REMAINING: "42", HEADER_RATE_LIMIT_MINUTE_REMAINING: "7"},
        ),
    )
    client, *_ = _fresh_client()
    async with client:
        await client.get_fixtures()

    assert client._daily_remaining == 42
    assert client._minute_remaining == 7


@respx.mock
async def test_rate_limit_sleep_does_not_block_other_keys() -> None:
    """Backoff on one key doesn't delay calls for different keys."""
    route_fixtures = respx.get(f"{BASE_URL}/fixtures").mock(
        return_value=httpx.Response(200, json=_wrap([_FIXTURE_ITEM]), headers=_RATE_LIMIT_HEADERS),
    )
    route_predictions = respx.get(f"{BASE_URL}/predictions").mock(
        return_value=httpx.Response(
            200,
            json=_wrap([{"predictions": None, "comparison": None, "h2h": None}]),
            headers=_RATE_LIMIT_HEADERS,
        ),
    )

    client, *_ = _fresh_client()
    # Simulate near-exhaustion: minute_remaining=2
    client._minute_remaining = 2

    async with client:
        # Both should complete; the lock is released before sleeping
        # so the second call can proceed while the first sleeps.
        results = await asyncio.gather(
            client.get_fixtures(),
            client.get_predictions(100),
        )

    assert len(results[0]) == 1
    assert results[1] is not None


@respx.mock
async def test_get_coverage_extracts_season() -> None:
    """get_coverage parses /leagues response and finds WC 2026 season."""
    leagues_item = {
        "league": {"id": 1, "name": "World Cup", "type": "Cup"},
        "country": {"name": "World"},
        "seasons": [
            {
                "year": 2026,
                "start": "2026-06-11",
                "end": "2026-07-19",
                "current": True,
                "coverage": {
                    "fixtures": {"events": False, "lineups": False, "statistics_fixtures": False, "statistics_players": False},
                    "standings": True,
                    "predictions": True,
                    "odds": False,
                    "injuries": False,
                    "players": False,
                    "top_scorers": False,
                    "top_assists": False,
                    "top_cards": False,
                },
            }
        ],
    }
    respx.get(f"{BASE_URL}/leagues").mock(
        return_value=httpx.Response(200, json=_wrap([leagues_item]), headers=_RATE_LIMIT_HEADERS),
    )
    client, *_ = _fresh_client()
    async with client:
        cov = await client.get_coverage()

    assert cov is not None
    assert cov.standings is True
    assert cov.predictions is True
    assert cov.fixtures_events is False
