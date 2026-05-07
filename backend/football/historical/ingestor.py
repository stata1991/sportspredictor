"""Async historical fixture ingestor.

Pulls completed fixtures + scores from API-Football for configured
league/season pairs.  Reuses :class:`APIFootballClient` for HTTP,
caching, and rate-limit handling.  Raw JSON responses are written to
``backend/football/historical/raw/`` for reproducibility — if a file
already exists for a (league, season) pair the API call is skipped
entirely.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from backend.cache import CacheClient
from backend.football.data_provider import APIFootballClient
from backend.shared.async_singleflight import AsyncSingleflight

logger = logging.getLogger(__name__)

RAW_DIR = Path(__file__).resolve().parent / "raw"

# ── Ingest configuration ────────────────────────────────────────────
# Each tuple: (description, league_id, season)
INGEST_PAIRS: list[tuple[str, int, int]] = [
    ("World Cup 2018", 1, 2018),
    ("World Cup 2022", 1, 2022),
    ("Euro 2020 (incl. quals)", 4, 2020),
    ("Euro 2024 (tournament)", 4, 2024),
    ("Euro 2024 Qualifying", 960, 2023),
    ("WC Qual Europe → 2022", 32, 2020),
    ("WC Qual Europe → 2026", 32, 2024),
    ("WC Qual South America → 2022", 34, 2022),
    ("WC Qual South America → 2026", 34, 2026),
    ("WC Qual Africa → 2022", 29, 2022),
    ("WC Qual Asia → 2022", 30, 2022),
    ("WC Qual CONCACAF → 2022", 31, 2022),
    ("WC Qual Oceania → 2026", 33, 2026),
]


def _raw_path(league_id: int, season: int) -> Path:
    """Return the file path for a cached raw JSON response."""
    return RAW_DIR / f"fixtures_league{league_id}_season{season}.json"


async def ingest_league_season(
    client: APIFootballClient,
    league_id: int,
    season: int,
    *,
    description: str = "",
    force: bool = False,
) -> list[dict[str, Any]]:
    """Fetch all fixtures for a league/season and cache to disk.

    If the raw JSON file already exists on disk and *force* is False,
    the file is read from disk instead of hitting the API.

    Returns the raw ``response`` array (list of fixture dicts).
    """
    path = _raw_path(league_id, season)

    if path.exists() and not force:
        logger.info(
            "Disk cache hit for %s (league=%d, season=%d) → %s",
            description, league_id, season, path,
        )
        with open(path) as f:
            return json.load(f)

    logger.info(
        "Fetching from API: %s (league=%d, season=%d)",
        description, league_id, season,
    )
    fixtures = await client.get_fixtures(league=league_id, season=season)

    # Serialize Pydantic models back to raw dicts for disk storage.
    raw = [fix.model_dump(mode="json") for fix in fixtures]

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(raw, f, indent=2)
    logger.info(
        "Wrote %d fixtures to %s", len(raw), path,
    )

    return raw


async def ingest_all(
    api_key: str,
    *,
    force: bool = False,
    pairs: list[tuple[str, int, int]] | None = None,
) -> dict[tuple[int, int], list[dict[str, Any]]]:
    """Ingest all configured league/season pairs.

    Returns a dict mapping ``(league_id, season)`` → raw fixture list.
    """
    targets = pairs or INGEST_PAIRS
    results: dict[tuple[int, int], list[dict[str, Any]]] = {}
    api_calls = 0

    cache = CacheClient()
    sf = AsyncSingleflight()

    async with APIFootballClient(api_key, cache, sf) as client:
        for description, league_id, season in targets:
            needs_api = not _raw_path(league_id, season).exists() or force
            raw = await ingest_league_season(
                client, league_id, season,
                description=description, force=force,
            )
            results[(league_id, season)] = raw
            if needs_api:
                api_calls += 1

    logger.info(
        "Ingest complete: %d league/season pairs, %d API calls, %d total fixtures",
        len(results), api_calls, sum(len(v) for v in results.values()),
    )
    return results
