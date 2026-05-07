"""Tests for Settings — env loading and DATABASE_URL transformation."""

from __future__ import annotations

import os
from unittest.mock import patch

from backend.shared.settings import Settings


class TestDatabaseUrlTransformation:
    """The postgresql:// → postgresql+psycopg:// validator."""

    def test_plain_postgresql_gets_rewritten(self) -> None:
        s = Settings(
            database_url="postgresql://user:pass@host:5432/db",
            _env_file=None,
        )
        assert s.database_url.startswith("postgresql+psycopg://")
        assert "user:pass@host:5432/db" in s.database_url

    def test_already_transformed_url_unchanged(self) -> None:
        url = "postgresql+psycopg://user:pass@host:5432/db"
        s = Settings(database_url=url, _env_file=None)
        assert s.database_url == url


class TestPasswordEncoding:
    """URL-encode only libpq-unsafe chars; never double-encode."""

    def test_plain_password_unchanged(self) -> None:
        s = Settings(
            database_url="postgresql+psycopg://user:abc123@host:5432/db",
            _env_file=None,
        )
        assert "abc123@host" in s.database_url

    def test_at_sign_in_password_gets_encoded(self) -> None:
        s = Settings(
            database_url="postgresql://user:p@ss@host:5432/db",
            _env_file=None,
        )
        assert "p%40ss@host" in s.database_url

    def test_already_encoded_password_not_double_encoded(self) -> None:
        s = Settings(
            database_url="postgresql+psycopg://user:p%40ss@host:5432/db",
            _env_file=None,
        )
        assert "p%40ss@host" in s.database_url
        assert "%2540" not in s.database_url


class TestExtraVarsIgnored:
    """extra='ignore' allows unknown env vars without ValidationError."""

    def test_extra_env_vars_do_not_break_settings(self) -> None:
        with patch.dict(os.environ, {
            "DATABASE_URL": "postgresql+psycopg://u:p@h:5432/db",
            "CACHE_ENABLED": "true",
            "CRICBUZZ_SCORECARD_ENDPOINT": "some-uuid",
            "UNKNOWN_VAR": "should-not-break",
        }):
            s = Settings(_env_file=None)
            assert s.database_url == "postgresql+psycopg://u:p@h:5432/db"
