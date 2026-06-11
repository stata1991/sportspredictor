"""Constants for the API-Football integration.

All values are for the *direct* api-sports.io subscription
(NOT the RapidAPI proxy).
"""

from __future__ import annotations

from typing import Final

# ── Base URL ──────────────────────────────────────────────────────────
BASE_URL = "https://v3.football.api-sports.io"

# ── World Cup identifiers ────────────────────────────────────────────
WC_LEAGUE_ID = 1
WC_SEASON = 2026

# ── HTTP defaults ────────────────────────────────────────────────────
DEFAULT_TIMEOUT_SECONDS = 10

# ── Request / response headers ───────────────────────────────────────
HEADER_API_KEY = "x-apisports-key"

# Daily quota (returned on every response)
HEADER_REQUESTS_LIMIT = "x-ratelimit-requests-limit"
HEADER_REQUESTS_REMAINING = "x-ratelimit-requests-remaining"

# Per-minute rate limit
HEADER_RATE_LIMIT_MINUTE = "x-ratelimit-limit"
HEADER_RATE_LIMIT_MINUTE_REMAINING = "x-ratelimit-remaining"

# ── Cache TTLs (seconds) per endpoint type ───────────────────────────
ENDPOINT_TTLS: Final[dict[str, int]] = {
    "fixtures_list": 3_600,
    # Live-aware fixtures list: short cache so in-play score/minute stay fresh
    # while at least one match is live (the frontend polls with ?live=1).
    "fixtures_list_live": 30,
    "fixture_detail_prematch": 300,
    "fixture_detail_live": 15,
    "lineups_prematch": 30,
    "lineups_live": 3_600,
    "events_live": 15,
    "statistics_live": 20,
    "team_statistics": 21_600,
    "odds": 600,
    "injuries": 1_800,
    "predictions": 21_600,
    "coverage": 3_600,
    "headtohead": 21_600,
    "team_last_fixtures": 3_600,
    "rounds": 3_600,
    "standings": 600,
}

# Stale backup TTL multiplier (for two-key stale-while-error pattern)
STALE_TTL_MULTIPLIER = 5

# ── Coverage expectations ────────────────────────────────────────────
# Flags expected to flip true 2-4 weeks before the tournament (June 11).
EXPECTED_COVERAGE: Final[frozenset[str]] = frozenset({
    "fixtures_events",
    "fixtures_lineups",
    "fixtures_statistics_fixtures",
    "injuries",
    "odds",
})
