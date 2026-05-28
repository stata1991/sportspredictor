"""Application settings loaded from environment / .env file."""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# Resolve backend/.env relative to this file so it works regardless of CWD.
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    """Central application settings.

    Reads from environment variables and optionally from ``backend/.env``.
    Extra env vars (e.g. CACHE_ENABLED, CRICBUZZ_SCORECARD_ENDPOINT) are
    silently ignored so existing cricket code can coexist.
    """

    model_config = SettingsConfigDict(
        env_file=str(_ENV_PATH),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str
    api_football_key: str | None = None
    rapidapi_key: str | None = None
    anthropic_api_key: str | None = None
    cricketdata_api_key: str | None = None
    environment: str = "development"

    # When True, use pre-fetch + single-shot Anthropic call instead of
    # multi-turn agent tool loop for reasoning generation.  Set to False
    # via USE_SINGLE_SHOT_REASONING=false for fast rollback.
    use_single_shot_reasoning: bool = True

    # Bearer token for the /admin/prewarm/upcoming endpoint.  Set via
    # PREWARM_API_KEY env var.  If unset, the endpoint rejects all
    # requests with 503 (fail-closed).
    prewarm_api_key: str | None = None

    # In-process pre-warm scheduler.  When enabled, an asyncio loop
    # fires _warm_fixtures_background on startup, then every
    # PREWARM_INTERVAL_SECONDS.  Set PREWARM_SCHEDULER_ENABLED=true
    # in EB env to activate; kill via env var without a code deploy.
    prewarm_scheduler_enabled: bool = False
    prewarm_interval_seconds: int = 900

    @field_validator("database_url", mode="before")
    @classmethod
    def _rewrite_pg_dialect(cls, v: str) -> str:
        """Rewrite ``postgresql://`` → ``postgresql+psycopg://`` for async.

        Also URL-encodes the password if it contains characters that
        confuse libpq's URL parser (e.g. ``@``).
        """
        if not isinstance(v, str):
            return v

        if v.startswith("postgresql://"):
            logger.warning(
                "Rewriting DATABASE_URL dialect: postgresql:// → postgresql+psycopg://"
            )
            v = "postgresql+psycopg" + v[len("postgresql"):]

        # Password encoding: libpq splits the connection URI on the FIRST @,
        # while Python's urlparse splits on the LAST @.  A raw @ in the
        # password (e.g. Supabase-generated passwords) causes libpq to
        # mis-parse the hostname.  We fix this by replacing only the
        # specific characters that break libpq — NOT by running blanket
        # urllib.parse.quote(), which would double-encode passwords that
        # already contain percent-encoded sequences (e.g. %40 → %2540).
        _LIBPQ_UNSAFE = {"@": "%40"}

        parsed = urlparse(v)
        if parsed.password and any(c in parsed.password for c in _LIBPQ_UNSAFE):
            encoded_pw = parsed.password
            for char, replacement in _LIBPQ_UNSAFE.items():
                encoded_pw = encoded_pw.replace(char, replacement)
            netloc = f"{parsed.username}:{encoded_pw}@{parsed.hostname}"
            if parsed.port:
                netloc += f":{parsed.port}"
            v = urlunparse((
                parsed.scheme, netloc, parsed.path,
                parsed.params, parsed.query, parsed.fragment,
            ))
            logger.warning("URL-encoded special characters in DATABASE_URL password")

        return v

    def __repr__(self) -> str:
        """Mask database_url to prevent password leaks in logs."""
        return f"Settings(environment={self.environment!r}, database_url=***)"


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton — safe to call from FastAPI ``Depends``."""
    return Settings()
