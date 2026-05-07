#!/usr/bin/env python3
"""Verify database connectivity. Does NOT create tables or run migrations."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from urllib.parse import urlparse

# Ensure repo root is importable.
_repo_root = str(Path(__file__).resolve().parent.parent)
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)


async def main() -> int:
    """Connect to the database and print version info."""
    try:
        from backend.shared.settings import get_settings
    except Exception as exc:
        print(f"✗ Failed to load settings: {exc}", file=sys.stderr)
        return 1

    settings = get_settings()
    if not settings.database_url:
        print("✗ DATABASE_URL is not set", file=sys.stderr)
        return 1

    parsed = urlparse(settings.database_url)
    safe_url = (
        f"{parsed.scheme}://{parsed.username}:***"
        f"@{parsed.hostname}:{parsed.port}{parsed.path}"
    )
    print(f"Connecting to: {safe_url}")

    try:
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine

        engine = create_async_engine(settings.database_url)
        async with engine.connect() as conn:
            version = (await conn.execute(text("SELECT version()"))).scalar()
            print(f"✓ PostgreSQL version: {version}")

            row = (
                await conn.execute(text("SELECT current_database(), current_user"))
            ).one()
            print(f"✓ Database: {row[0]}, User: {row[1]}")

        await engine.dispose()
        print("✓ Connection verified successfully")
        return 0

    except Exception as exc:
        print(f"✗ Connection failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
