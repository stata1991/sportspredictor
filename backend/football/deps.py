"""FastAPI dependency injection for football endpoints."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import HTTPException

from backend.cache import cache as _cache_singleton
from backend.football.agent.client import AnthropicAgentClient
from backend.football.data_provider import APIFootballClient
from backend.shared.async_singleflight import AsyncSingleflight
from backend.shared.settings import get_settings

# Module-level singleton — must persist across requests so concurrent
# calls for the same cache key are actually deduplicated.
_singleflight = AsyncSingleflight()


async def get_football_client() -> AsyncGenerator[APIFootballClient, None]:
    """Provide an ``APIFootballClient`` as an async context manager.

    Raises HTTP 503 immediately if ``API_FOOTBALL_KEY`` is not configured.
    """
    settings = get_settings()
    if not settings.api_football_key:
        raise HTTPException(
            status_code=503, detail="API_FOOTBALL_KEY not configured"
        )
    async with APIFootballClient(
        settings.api_football_key, _cache_singleton, _singleflight
    ) as client:
        yield client


def get_agent_client() -> AnthropicAgentClient | None:
    """Provide an ``AnthropicAgentClient``, or ``None`` if unconfigured.

    Unlike ``get_football_client``, this does NOT raise — reasoning is
    optional.  Routes check for None and skip reasoning gracefully.
    """
    settings = get_settings()
    if not settings.anthropic_api_key:
        return None
    return AnthropicAgentClient(api_key=settings.anthropic_api_key)
