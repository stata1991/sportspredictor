"""Tests for the async engine's hang-defense connect_args (EVAL-3 / TRACK-4).

TRACK-4 root cause: a scheduler cycle hung 12.5h on an *uncapped* DB await
against the Supabase session pooler.  httpx upstream calls are capped at 10s;
DB ops were not.  The engine now sets a server-side ``statement_timeout`` and a
TCP ``connect_timeout`` so a stalled pooler connection raises fast (defense in
depth under the scheduler's per-cycle ``wait_for``) instead of blocking forever.

The libpq-style ``options="-c statement_timeout=..."`` + ``connect_timeout``
syntax is **psycopg-specific** — asyncpg rejects both (it uses ``timeout`` and
``server_settings``).  These tests pin the driver and the config so a future
dialect swap can't silently drop the timeout or pass syntax the driver ignores.
"""

from __future__ import annotations


class TestEngineHangDefense:
    def test_driver_is_psycopg(self):
        """The libpq connect_args below are only valid for the psycopg driver.
        If this ever flips to asyncpg, the options string is silently wrong."""
        from backend.shared.db import engine

        assert engine.dialect.driver == "psycopg"

    def test_connect_args_set_statement_and_connect_timeout(self):
        """Engine must carry a server-side statement_timeout and a connect
        timeout so a stalled Supabase pooler connection fails fast.

        SQLAlchemy merges the explicit ``connect_args`` into the per-connection
        params (``cparams``) captured by the pool's connect closure — that
        merged dict is the source of truth for what the DBAPI actually sees."""
        import inspect

        from backend.shared.db import engine

        cparams = dict(
            inspect.getclosurevars(engine.sync_engine.pool._creator).nonlocals[
                "cparams"
            ]
        )

        assert cparams.get("connect_timeout") == 10
        # statement_timeout passed via libpq startup options (milliseconds).
        assert "statement_timeout=30000" in cparams.get("options", "")
