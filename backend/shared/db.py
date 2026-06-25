"""SQLAlchemy 2.0 async engine and session configuration.

Configured for Supabase **Session pooler** (port 5432), driver = **psycopg v3**
(settings rewrites ``postgresql://`` → ``postgresql+psycopg://``).

EVAL-4 (TRACK-7): a grading cycle's first DB await wedged for 16h on a
black-holed pooler connection (idle-reaped with no RST), and EVERY EVAL-3
defense missed it:

- ``pool_pre_ping`` issues its own ``SELECT 1`` on checkout — but on a
  black-holed socket that ping's READ blocks forever (the write succeeds at
  the TCP layer; nothing ever answers). pre_ping only rescues you when the
  dead connection ERRORS quickly (RST / conn-refused), not when it silently
  hangs.
- server-side ``statement_timeout`` never starts: the server never receives
  the query, so it cannot time it out.
- the per-cycle ``asyncio.timeout`` could not unwind: its cancellation had to
  pass through that same blocked socket read in ``__aexit__``.

The missing layer is an **OS-level dead-peer detector**: TCP keepalives.
libpq (hence psycopg) honours ``keepalives*`` connect params; the kernel
probes an idle socket and, on a black hole, fails it with ETIMEDOUT in a
bounded window (~30s idle + 3×10s probes ≈ 60s). That turns pre_ping / any
query / teardown from "hang forever" into "raise in ≤~60s" — which is what
lets the EVAL-4 abandon-guard (scheduler.py) surface an event and tick on.

``pool_recycle`` retires a connection before the pooler's idle reaper can
black-hole it — the first line of defense (keepalives are the backstop for a
connection that dies mid-window).
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

# EVAL-4: 1800s (one eval interval) let a connection sit at the reaper's edge
# — the 08:05Z hang was on a ~30-min-idle connection. Recycle well under the
# pooler's idle window so connections retire BEFORE the pooler silently drops
# them. ASSUMPTION: Supabase Supavisor's session-pooler idle timeout is not
# documented to us; 300s is chosen conservatively below any commonly-observed
# pooler idle window. If the real value is learned, set recycle to ~80% of it.
# Churn cost is trivial at our 15/30-min cadence (a fresh connect is ~50-100ms).
POOL_RECYCLE_SECONDS = 300

# EVAL-4 / TRACK-7 defense-in-depth. Layered, because each cap covers a
# different failure and the 16h hang slipped between them:
#   - keepalives* (THE EVAL-4 FIX): OS-level dead-peer detection. The psycopg
#     driver has no asyncpg-style ``command_timeout``; libpq TCP keepalives
#     are the client-side equivalent. On a black-holed socket the kernel fails
#     the fd in ~30s idle + 3×10s probes ≈ 60s, so a dead connection RAISES
#     instead of hanging pre_ping / query / teardown forever. THIS is what
#     EVAL-3 lacked.
#   - statement_timeout (30s, server-side): caps a query the server is
#     actively running. Does NOT cover a dead-socket acquire or a blocked
#     teardown (server never sees the statement) — exactly why it did not
#     prevent the 08:05Z hang.
#   - connect_timeout (10s): caps establishing a NEW TCP connection only.
#   - SQLAlchemy pool_timeout (default 30s): caps waiting for a pooled slot.
CONNECT_ARGS = {
    "connect_timeout": 10,
    "options": "-c statement_timeout=30000",
    # libpq TCP keepalives — bound a half-open/black-holed socket.
    "keepalives": 1,
    "keepalives_idle": 30,
    "keepalives_interval": 10,
    "keepalives_count": 3,
}

engine = create_async_engine(
    _settings.database_url,
    pool_size=5,
    max_overflow=5,
    pool_pre_ping=True,
    pool_recycle=POOL_RECYCLE_SECONDS,
    connect_args=CONNECT_ARGS,
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
