"""API-Football data provider.

Async HTTP client for the api-sports.io v3 API with:
- In-memory caching (fresh + stale backup keys)
- AsyncSingleflight deduplication
- Rate-limit guard from response headers
- Structured logging on every request
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable

import httpx

from backend.cache import CacheClient
from backend.football.constants import (
    BASE_URL,
    DEFAULT_TIMEOUT_SECONDS,
    ENDPOINT_TTLS,
    HEADER_API_KEY,
    HEADER_RATE_LIMIT_MINUTE_REMAINING,
    HEADER_REQUESTS_REMAINING,
    STALE_TTL_MULTIPLIER,
    WC_LEAGUE_ID,
    WC_SEASON,
)
from backend.football.exceptions import (
    APIFootballError,
    ParseError,
    PlanLimitationError,
    QuotaExhaustedError,
    RateLimitError,
    UpstreamError,
)
from backend.football.schemas import (
    AFCoverage,
    AFEvent,
    AFFixture,
    AFInjury,
    AFLeagueWithSeasons,
    AFLineup,
    AFOdds,
    AFPrediction,
    AFStandingsResponse,
)
from backend.shared.async_singleflight import AsyncSingleflight

logger = logging.getLogger(__name__)


# In-play status codes (mirrors routes._LIVE_STATUSES / frontend IN_PLAY).
_LIVE_STATUS_SHORT: frozenset[str] = frozenset(
    {"1H", "2H", "HT", "ET", "BT", "P", "LIVE"}
)


def _fixtures_list_ttl(items: list[dict[str, Any]]) -> int:
    """Live-aware TTL for the NON-live fixtures list (LIVETAB-5).

    Returns the short live TTL when the schedule is volatile — any fixture
    in-play, OR kicking off within the long-TTL window (so a freshly-written
    long entry can't swallow a kickoff that lands before it expires).
    Otherwise the long schedule TTL. This keeps the Schedule tab fresh
    during and just before matches without refetching the static schedule
    overnight. One shared key, so the short-TTL refetches are trivial.
    """
    short_ttl = ENDPOINT_TTLS["fixtures_list_live"]
    long_ttl = ENDPOINT_TTLS["fixtures_list"]
    now = time.time()
    for item in items:
        fixture = item.get("fixture") or {}
        status = (fixture.get("status") or {}).get("short")
        if status in _LIVE_STATUS_SHORT:
            return short_ttl
        ts = fixture.get("timestamp")
        # Kicks off within the window we'd otherwise cache for → don't cache
        # long, or the kickoff would go unseen until the entry expires.
        if isinstance(ts, (int, float)) and 0 <= ts - now <= long_ttl:
            return short_ttl
    return long_ttl


class APIFootballClient:
    """Async client for the API-Football v3 REST API.

    Usage::

        async with APIFootballClient(api_key, cache, singleflight) as client:
            fixtures = await client.get_fixtures()
    """

    def __init__(
        self,
        api_key: str,
        cache: CacheClient,
        singleflight: AsyncSingleflight,
    ) -> None:
        self._api_key = api_key
        self._cache = cache
        self._sf = singleflight
        self._http: httpx.AsyncClient | None = None

        # Rate-limit tracking
        self._minute_window_start: float = 0.0
        self._requests_this_minute: int = 0
        self._daily_remaining: int | None = None
        self._minute_remaining: int | None = None
        self._lock: asyncio.Lock = asyncio.Lock()

    async def __aenter__(self) -> APIFootballClient:
        self._http = httpx.AsyncClient(
            base_url=BASE_URL,
            headers={HEADER_API_KEY: self._api_key},
            timeout=DEFAULT_TIMEOUT_SECONDS,
        )
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._http:
            await self._http.aclose()
            self._http = None

    # ── Cache key construction ─────────────────────────────────────

    @staticmethod
    def _cache_key(method: str, params: dict[str, Any]) -> str:
        """Build ``af:v1:<method>:<k1=v1&k2=v2>`` from sorted params."""
        sorted_parts = "&".join(
            f"{k}={v}" for k, v in sorted(params.items())
        )
        return f"af:v1:{method}:{sorted_parts}"

    @staticmethod
    def _stale_key(fresh_key: str) -> str:
        """Stale backup key = fresh key + ``:stale``."""
        return f"{fresh_key}:stale"

    # ── Core request helper ────────────────────────────────────────

    async def _request(
        self,
        endpoint: str,
        params: dict[str, Any],
        *,
        cache_method: str,
        ttl: int,
        stale_fallback: bool = True,
        ttl_resolver: Callable[[list[dict[str, Any]]], int] | None = None,
    ) -> list[dict[str, Any]]:
        """Central HTTP + cache + error-handling pipeline.

        Returns the ``response`` array from the API-Football envelope
        as a list of raw dicts.  Empty list when ``results=0`` (valid
        query, no data yet).  Raises on errors.

        Callers parse items into typed models; single-item methods
        should treat an empty list as ``None``.

        Parameters
        ----------
        endpoint:
            API path, e.g. ``"/fixtures"``.
        params:
            Query parameters for the request.
        cache_method:
            Logical name for cache key construction
            (e.g. ``"fixtures"``, ``"fixture"``).
        ttl:
            Fresh-cache TTL in seconds.
        stale_fallback:
            If True (default), fall back to the stale cache key on
            upstream errors.  Set to False for volatile live-match
            data where stale values are worse than a clean failure.

        Flow
        ----
        1. Check fresh cache → return on hit
        2. Deduplicate via AsyncSingleflight
        3. Acquire rate-limit lock; sleep if near limit
        4. Make HTTP request to API-Football
        5. Update rate-limit counters from response headers
        6. Classify errors (4xx/5xx, ``errors`` dict, plan limitations)
        7. On success: write fresh key + stale backup key
        8. On upstream error: fall back to stale key if available
        9. Log structured data on every request
        """
        if self._http is None:
            raise RuntimeError(
                "APIFootballClient must be used as async context manager"
            )

        # Fail-fast daily quota guard.
        # Once exhausted, every call fails immediately without
        # touching cache or singleflight.
        if self._daily_remaining is not None and self._daily_remaining <= 0:
            raise QuotaExhaustedError("daily request quota exhausted")

        key = self._cache_key(cache_method, params)

        # ── 1. Fresh cache check ──────────────────────────────────
        cached = self._cache.get(key)
        if cached is not None:
            logger.info(
                "api_football_request",
                extra={
                    "endpoint": endpoint,
                    "params": params,
                    "cache_hit": True,
                    "upstream_status": "cached",
                    "response_time_ms": 0,
                    "daily_remaining": self._daily_remaining,
                    "minute_remaining": self._minute_remaining,
                },
            )
            return cached

        # ── 2. Deduplicate via singleflight ───────────────────────
        async def _fetch() -> list[dict[str, Any]]:
            # ── 3. Rate-limit guard ───────────────────────────────
            sleep_secs = 0.0
            near_limit_value = None

            async with self._lock:
                now = time.time()
                current_minute = int(now) // 60
                stored_minute = int(self._minute_window_start) // 60

                if current_minute != stored_minute:
                    self._minute_window_start = float(current_minute * 60)
                    self._requests_this_minute = 0

                if (
                    self._minute_remaining is not None
                    and self._minute_remaining <= 5
                ):
                    near_limit_value = self._minute_remaining
                    next_boundary = (current_minute + 1) * 60
                    sleep_secs = max(0.0, next_boundary - now)

                self._requests_this_minute += 1

            # Sleep AFTER releasing lock — other tasks for different
            # keys can proceed while this one backs off.
            if sleep_secs > 0:
                logger.warning(
                    "Rate limit near exhaustion "
                    "(minute_remaining=%d), sleeping %.1fs",
                    near_limit_value,
                    sleep_secs,
                )
                await asyncio.sleep(sleep_secs)
                async with self._lock:
                    self._requests_this_minute = 0
                    self._minute_remaining = None

            # ── 4. HTTP GET ───────────────────────────────────────
            t0 = time.monotonic()
            stale_key = self._stale_key(key)

            try:
                resp = await self._http.get(endpoint, params=params)
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                elapsed_ms = round((time.monotonic() - t0) * 1000, 1)
                logger.error(
                    "api_football_request",
                    extra={
                        "endpoint": endpoint,
                        "params": params,
                        "cache_hit": False,
                        "upstream_status": "error",
                        "response_time_ms": elapsed_ms,
                        "error": f"{type(exc).__name__}: {exc}",
                        "daily_remaining": self._daily_remaining,
                        "minute_remaining": self._minute_remaining,
                    },
                )
                if stale_fallback:
                    stale = self._cache.get(stale_key)
                    if stale is not None:
                        logger.warning(
                            "Returning stale cache for %s after "
                            "upstream failure: %s",
                            cache_method,
                            type(exc).__name__,
                        )
                        return stale
                raise UpstreamError(detail=str(exc)) from exc

            elapsed_ms = round((time.monotonic() - t0) * 1000, 1)

            # ── 5. Update rate-limit state from headers ───────────
            hdr_daily = resp.headers.get(HEADER_REQUESTS_REMAINING)
            if hdr_daily is not None:
                try:
                    self._daily_remaining = int(hdr_daily)
                except ValueError:
                    pass

            hdr_minute = resp.headers.get(
                HEADER_RATE_LIMIT_MINUTE_REMAINING
            )
            if hdr_minute is not None:
                try:
                    self._minute_remaining = int(hdr_minute)
                except ValueError:
                    pass

            status = resp.status_code

            # ── 6. HTTP >= 500 → stale fallback or UpstreamError ──
            if status >= 500:
                logger.error(
                    "api_football_request",
                    extra={
                        "endpoint": endpoint,
                        "params": params,
                        "cache_hit": False,
                        "upstream_status": status,
                        "response_time_ms": elapsed_ms,
                        "daily_remaining": self._daily_remaining,
                        "minute_remaining": self._minute_remaining,
                    },
                )
                if stale_fallback:
                    stale = self._cache.get(stale_key)
                    if stale is not None:
                        logger.warning(
                            "Returning stale cache for %s after "
                            "upstream failure: UpstreamError",
                            cache_method,
                        )
                        return stale
                raise UpstreamError(status_code=status)

            # ── 7. HTTP 4xx → UpstreamError, NO stale fallback ────
            if status >= 400:
                logger.error(
                    "api_football_request",
                    extra={
                        "endpoint": endpoint,
                        "params": params,
                        "cache_hit": False,
                        "upstream_status": status,
                        "response_time_ms": elapsed_ms,
                        "error": resp.text[:200],
                        "daily_remaining": self._daily_remaining,
                        "minute_remaining": self._minute_remaining,
                    },
                )
                raise UpstreamError(
                    status_code=status, detail=resp.text[:200]
                )

            # ── 8. Parse body and check errors ────────────────────
            body = resp.json()
            errors = body.get("errors", [])
            response_data = body.get("response", [])

            if errors:
                # errors can be dict or list per API-Football docs
                if isinstance(errors, dict):
                    if any(k.lower() == "plan" for k in errors):
                        raise PlanLimitationError(str(errors))
                    if any(k.lower() == "ratelimit" for k in errors):
                        raise RateLimitError()
                    raise APIFootballError(str(errors))
                # list (or other iterable) of error strings
                raise APIFootballError(
                    "; ".join(str(e) for e in errors)
                )

            # ── 9. Cache the successful response ──────────────────
            # The write TTL may depend on the response (e.g. the non-live
            # fixtures list shortens its TTL when a match is live/imminent).
            # This does NOT change the freshness check, which still judges by
            # the stored entry's TTL — it only lets the writer pick that TTL.
            write_ttl = (
                ttl_resolver(response_data)
                if ttl_resolver is not None
                else ttl
            )
            self._cache.set(key, response_data, write_ttl)
            if stale_fallback:
                self._cache.set(
                    stale_key,
                    response_data,
                    write_ttl * STALE_TTL_MULTIPLIER,
                )

            # ── 10. Log success ───────────────────────────────────
            logger.info(
                "api_football_request",
                extra={
                    "endpoint": endpoint,
                    "params": params,
                    "cache_hit": False,
                    "upstream_status": status,
                    "response_time_ms": elapsed_ms,
                    "results": body.get("results", 0),
                    "daily_remaining": self._daily_remaining,
                    "minute_remaining": self._minute_remaining,
                },
            )

            return response_data

        return await self._sf.call(key, _fetch)

    # ── Public methods ─────────────────────────────────────────────

    async def get_fixtures(
        self,
        league: int = WC_LEAGUE_ID,
        season: int = WC_SEASON,
        *,
        live: bool = False,
    ) -> list[AFFixture]:
        """List all fixtures for a league/season.

        Live and non-live use **distinct cache keys** (``fixtures_live`` vs
        ``fixtures``) — LIVETAB-5. Sharing one key let a non-live 3600s write
        poison the 30s live read for up to an hour (the freshness check
        judges by the stored entry's TTL, not the reader's), so the Live tab
        served stale ``NS`` through whole matches.

        - ``live=True``: own short-TTL key (``fixtures_list_live``), never
          touched by a non-live write.
        - ``live=False``: live-aware TTL (:func:`_fixtures_list_ttl`) — short
          while any fixture is in-play or imminent, long only when genuinely
          idle — so the Schedule tab stays fresh during matches too.
        """
        if live:
            items = await self._request(
                "/fixtures",
                {"league": league, "season": season},
                cache_method="fixtures_live",
                ttl=ENDPOINT_TTLS["fixtures_list_live"],
            )
        else:
            items = await self._request(
                "/fixtures",
                {"league": league, "season": season},
                cache_method="fixtures",
                ttl=ENDPOINT_TTLS["fixtures_list"],
                ttl_resolver=_fixtures_list_ttl,
            )
        return [AFFixture.model_validate(item) for item in items]

    async def get_fixture(self, fixture_id: int) -> AFFixture | None:
        """Single fixture by ID.  Returns None if not found."""
        items = await self._request(
            "/fixtures",
            {"id": fixture_id},
            cache_method="fixture",
            ttl=ENDPOINT_TTLS["fixture_detail_prematch"],
        )
        if not items:
            return None
        return AFFixture.model_validate(items[0])

    async def get_coverage(self) -> AFCoverage | None:
        """Coverage flags for WC 2026 from the ``/leagues`` endpoint."""
        items = await self._request(
            "/leagues",
            {"id": WC_LEAGUE_ID, "season": WC_SEASON},
            cache_method="coverage",
            ttl=ENDPOINT_TTLS["coverage"],
        )
        if not items:
            return None
        lws = AFLeagueWithSeasons.model_validate(items[0])
        for season in lws.seasons:
            if season.year == WC_SEASON:
                return season.coverage
        return None

    async def get_lineups(self, fixture_id: int) -> list[AFLineup]:
        """Lineups for a fixture."""
        items = await self._request(
            "/fixtures/lineups",
            {"fixture": fixture_id},
            cache_method="lineups",
            ttl=ENDPOINT_TTLS["lineups_prematch"],
        )
        return [AFLineup.model_validate(item) for item in items]

    async def get_events(self, fixture_id: int) -> list[AFEvent]:
        """Match events (goals, cards, subs) for a fixture."""
        items = await self._request(
            "/fixtures/events",
            {"fixture": fixture_id},
            cache_method="events",
            ttl=ENDPOINT_TTLS["events_live"],
            stale_fallback=False,
        )
        return [AFEvent.model_validate(item) for item in items]

    async def get_statistics(self, fixture_id: int) -> list[dict[str, Any]]:
        """Team statistics for a fixture (kept as raw dicts)."""
        return await self._request(
            "/fixtures/statistics",
            {"fixture": fixture_id},
            cache_method="statistics",
            ttl=ENDPOINT_TTLS["statistics_live"],
            stale_fallback=False,
        )

    async def get_team_statistics(
        self,
        team_id: int,
        league: int = WC_LEAGUE_ID,
        season: int = WC_SEASON,
    ) -> dict[str, Any] | None:
        """Aggregate team statistics for a league/season."""
        items = await self._request(
            "/teams/statistics",
            {"team": team_id, "league": league, "season": season},
            cache_method="team_statistics",
            ttl=ENDPOINT_TTLS["team_statistics"],
        )
        if not items:
            return None
        return items[0]

    async def get_odds(self, fixture_id: int) -> list[AFOdds]:
        """Odds for a fixture."""
        items = await self._request(
            "/odds",
            {"fixture": fixture_id},
            cache_method="odds",
            ttl=ENDPOINT_TTLS["odds"],
        )
        return [AFOdds.model_validate(item) for item in items]

    async def get_injuries(
        self,
        league: int = WC_LEAGUE_ID,
        season: int = WC_SEASON,
    ) -> list[AFInjury]:
        """Injuries for a league/season."""
        items = await self._request(
            "/injuries",
            {"league": league, "season": season},
            cache_method="injuries",
            ttl=ENDPOINT_TTLS["injuries"],
        )
        return [AFInjury.model_validate(item) for item in items]

    async def get_predictions(self, fixture_id: int) -> AFPrediction | None:
        """API-Football ML prediction for a fixture."""
        items = await self._request(
            "/predictions",
            {"fixture": fixture_id},
            cache_method="predictions",
            ttl=ENDPOINT_TTLS["predictions"],
        )
        if not items:
            return None
        return AFPrediction.model_validate(items[0])

    async def get_head_to_head(
        self,
        home_team_id: int,
        away_team_id: int,
        last: int = 10,
    ) -> list[AFFixture]:
        """Head-to-head fixtures between two teams."""
        h2h_str = f"{home_team_id}-{away_team_id}"
        items = await self._request(
            "/fixtures/headtohead",
            {"h2h": h2h_str, "last": last},
            cache_method="headtohead",
            ttl=ENDPOINT_TTLS["headtohead"],
        )
        return [AFFixture.model_validate(item) for item in items]

    async def get_team_last_fixtures(
        self,
        team_id: int,
        last: int = 5,
    ) -> list[AFFixture]:
        """Last N fixtures for a team (any league)."""
        items = await self._request(
            "/fixtures",
            {"team": team_id, "last": last},
            cache_method="team_last_fixtures",
            ttl=ENDPOINT_TTLS["team_last_fixtures"],
        )
        return [AFFixture.model_validate(item) for item in items]

    async def get_standings(
        self,
        league: int = WC_LEAGUE_ID,
        season: int = WC_SEASON,
    ) -> AFStandingsResponse | None:
        """Standings for a league/season (group tables)."""
        items = await self._request(
            "/standings",
            {"league": league, "season": season},
            cache_method="standings",
            ttl=ENDPOINT_TTLS["standings"],
        )
        if not items:
            return None
        return AFStandingsResponse.model_validate(items[0])

    async def get_rounds(
        self,
        league: int = WC_LEAGUE_ID,
        season: int = WC_SEASON,
    ) -> list[str]:
        """Available rounds for a league/season (e.g. 'Group A - 1', 'Final')."""
        items = await self._request(
            "/fixtures/rounds",
            {"league": league, "season": season},
            cache_method="rounds",
            ttl=ENDPOINT_TTLS["rounds"],
        )
        # API-Football returns rounds as a flat list of strings
        # in the response array (not wrapped in objects).
        return [str(r) for r in items]

    async def get_teams_for_league(
        self,
        league: int = WC_LEAGUE_ID,
        season: int = WC_SEASON,
    ) -> list[dict[str, Any]]:
        """Teams participating in a league/season (kept as raw dicts)."""
        return await self._request(
            "/teams",
            {"league": league, "season": season},
            cache_method="teams",
            ttl=ENDPOINT_TTLS["fixtures_list"],
        )
