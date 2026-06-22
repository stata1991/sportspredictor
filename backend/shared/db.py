"""SQLAlchemy 2.0 async engine and session configuration.

Configured for Supabase **Session pooler** (port 5432):

- **IPv4 compatible** — works from all deployment environments.
- **Prepared statements supported** — no need to set ``prepare_threshold=None``.
- ``pool_recycle=1800`` (30 min) — Supabase pooler closes idle connections;
  recycling prevents stale-connection errors after periods of low traffic.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.shared.settings import get_settings

_settings = get_settings()

engine = create_async_engine(
    _settings.database_url,
    pool_size=5,
    max_overflow=5,
    pool_pre_ping=True,
    pool_recycle=1800,
    # EVAL-3 / TRACK-4 defense-in-depth: cap DB ops so a stalled Supabase
    # pooler connection raises fast instead of hanging the await forever
    # (httpx is capped at 10s; the DB was not). statement_timeout is a
    # SERVER-SIDE cap on any single query (30s — orders of magnitude above
    # our sub-second queries) that persists on the session pooler; this is
    # what lets the scheduler's per-cycle wait_for cancel cleanly rather
    # than blocking on an unresponsive socket. connect_timeout caps TCP
    # connect to the pooler. SQLAlchemy's pool_timeout (default 30s) already
    # caps waiting for a pooled connection.
    connect_args={
        "connect_timeout": 10,
        "options": "-c statement_timeout=30000",
    },
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    expire_on_commit=False,
    autoflush=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async session for FastAPI route handlers via ``Depends``."""
    async with AsyncSessionLocal() as session:
        yield session


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Async context manager for use in scripts and background tasks."""
    async with AsyncSessionLocal() as session:
        yield session
