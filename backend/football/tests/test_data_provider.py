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


# ── Fixtures-list cache poisoning fix (LIVETAB-5) ─────────────────────

import time as _time  # noqa: E402

from backend.football.constants import ENDPOINT_TTLS  # noqa: E402
from backend.football.data_provider import (  # noqa: E402
    _fixture_detail_ttl,
    _fixtures_list_ttl,
)


def _live_item(status: str = "2H", elapsed: int = 55, ts: int | None = None) -> dict:
    """A fixture item with an in-play status (deep-copied from _FIXTURE_ITEM)."""
    import copy
    item = copy.deepcopy(_FIXTURE_ITEM)
    item["fixture"]["status"] = {"long": "Second Half", "short": status, "elapsed": elapsed}
    item["goals"] = {"home": 1, "away": 0}
    if ts is not None:
        item["fixture"]["timestamp"] = ts
    return item


def test_live_and_nonlive_fixtures_keys_differ() -> None:
    """The two modes must use DISTINCT cache keys (no shared poisoning)."""
    p = {"league": 1, "season": 2026}
    assert (
        APIFootballClient._cache_key("fixtures", p)
        != APIFootballClient._cache_key("fixtures_live", p)
    )


@respx.mock
async def test_nonlive_write_does_not_poison_live_read() -> None:
    """The LIVETAB-4 scenario: a non-live NS write must NOT satisfy a later
    live read. Distinct keys → the live read refetches and sees the kickoff."""
    route = respx.get(f"{BASE_URL}/fixtures").mock(
        side_effect=[
            # 1st call (non-live): everything NS.
            httpx.Response(200, json=_wrap([_FIXTURE_ITEM]), headers=_RATE_LIMIT_HEADERS),
            # 2nd call (live): the match has kicked off.
            httpx.Response(200, json=_wrap([_live_item()]), headers=_RATE_LIMIT_HEADERS),
        ]
    )
    client, *_ = _fresh_client()
    async with client:
        non_live = await client.get_fixtures(live=False)   # writes "fixtures" key (NS, long TTL)
        live = await client.get_fixtures(live=True)         # distinct key → must refetch

    assert non_live[0].fixture.status.short == "NS"
    assert live[0].fixture.status.short == "2H"             # NOT the stale NS
    assert route.call_count == 2                            # both hit upstream (keys differ)


@respx.mock
async def test_live_list_has_its_own_cached_key() -> None:
    """Two live reads share the live key (cached), independent of non-live."""
    route = respx.get(f"{BASE_URL}/fixtures").mock(
        return_value=httpx.Response(200, json=_wrap([_live_item()]), headers=_RATE_LIMIT_HEADERS),
    )
    client, cache, _ = _fresh_client()
    async with client:
        await client.get_fixtures(live=True)
        await client.get_fixtures(live=True)   # cached on the live key

    assert route.call_count == 1
    live_key = APIFootballClient._cache_key("fixtures_live", {"league": 1, "season": 2026})
    assert cache.get(live_key) is not None


# ── Live-aware non-live TTL (Schedule freshness) ──────────────────────


def test_fixtures_list_ttl_short_when_a_match_is_live() -> None:
    items = [{"fixture": {"status": {"short": "2H"}, "timestamp": int(_time.time())}}]
    assert _fixtures_list_ttl(items) == ENDPOINT_TTLS["fixtures_list_live"]


def test_fixtures_list_ttl_short_when_a_kickoff_is_imminent() -> None:
    # NS but kicks off in 10 min — must not be cached for the long window,
    # or the kickoff would go unseen until the entry expires.
    soon = int(_time.time()) + 600
    items = [{"fixture": {"status": {"short": "NS"}, "timestamp": soon}}]
    assert _fixtures_list_ttl(items) == ENDPOINT_TTLS["fixtures_list_live"]


def test_fixtures_list_ttl_long_when_idle() -> None:
    # Nothing live, next kickoff well beyond the long window → long TTL,
    # so we don't refetch the static schedule overnight (no regression).
    far = int(_time.time()) + ENDPOINT_TTLS["fixtures_list"] + 7200
    items = [{"fixture": {"status": {"short": "NS"}, "timestamp": far}}]
    assert _fixtures_list_ttl(items) == ENDPOINT_TTLS["fixtures_list"]


def test_fixtures_list_ttl_long_when_empty() -> None:
    assert _fixtures_list_ttl([]) == ENDPOINT_TTLS["fixtures_list"]


def test_fixtures_list_ttl_any_live_fixture_shortens_whole_list() -> None:
    far = int(_time.time()) + ENDPOINT_TTLS["fixtures_list"] + 7200
    items = [
        {"fixture": {"status": {"short": "FT"}, "timestamp": far - 100000}},
        {"fixture": {"status": {"short": "NS"}, "timestamp": far}},
        {"fixture": {"status": {"short": "1H"}, "timestamp": int(_time.time())}},  # one live
    ]
    assert _fixtures_list_ttl(items) == ENDPOINT_TTLS["fixtures_list_live"]


# ── Live-detail freshness fix (POLL-FIX-1) ────────────────────────────


def test_fixture_detail_ttl_short_when_live() -> None:
    items = [{"fixture": {"status": {"short": "1H"}, "timestamp": int(_time.time())}}]
    assert _fixture_detail_ttl(items) == ENDPOINT_TTLS["fixture_detail_live"]   # 15s


def test_fixture_detail_ttl_short_when_imminent() -> None:
    soon = int(_time.time()) + 120
    items = [{"fixture": {"status": {"short": "NS"}, "timestamp": soon}}]
    assert _fixture_detail_ttl(items) == ENDPOINT_TTLS["fixture_detail_live"]


def test_fixture_detail_ttl_long_when_prematch() -> None:
    far = int(_time.time()) + ENDPOINT_TTLS["fixture_detail_prematch"] + 7200
    items = [{"fixture": {"status": {"short": "NS"}, "timestamp": far}}]
    assert _fixture_detail_ttl(items) == ENDPOINT_TTLS["fixture_detail_prematch"]  # 300s


def test_fixture_detail_ttl_long_when_finished() -> None:
    # FT in the past → not live, not imminent → long (terminal, fine to cache).
    items = [{"fixture": {"status": {"short": "FT"}, "timestamp": int(_time.time()) - 7200}}]
    assert _fixture_detail_ttl(items) == ENDPOINT_TTLS["fixture_detail_prematch"]


@respx.mock
async def test_live_fixture_detail_not_frozen_on_300s_entry() -> None:
    """A live fixture's detail must refresh on the short TTL, not be frozen
    for 300s. We can't fast-forward the clock, so assert the write TTL the
    resolver chooses for a live fixture is the 15s key, not 300s."""
    captured: dict = {}
    client, cache, _ = _fresh_client()

    real_set = cache.set

    def _spy_set(key, value, ttl):  # capture the FRESH-key TTL (not the :stale backup)
        if "fixture:" in key and "fixtures" not in key and not key.endswith(":stale"):
            captured["ttl"] = ttl
        return real_set(key, value, ttl)

    cache.set = _spy_set  # type: ignore[method-assign]
    respx.get(f"{BASE_URL}/fixtures").mock(
        return_value=httpx.Response(200, json=_wrap([_live_item("1H", 12)]), headers=_RATE_LIMIT_HEADERS),
    )
    async with client:
        fx = await client.get_fixture(100)

    assert fx is not None and fx.fixture.status.short == "1H"
    assert captured.get("ttl") == ENDPOINT_TTLS["fixture_detail_live"]  # 15s, not 300s
