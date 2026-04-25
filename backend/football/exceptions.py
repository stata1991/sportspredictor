"""Exception hierarchy for the API-Football data provider.

::

    APIFootballError (base)
    ├── UpstreamError       — 5xx / network failures
    ├── RateLimitError      — per-minute rate limit hit
    ├── QuotaExhaustedError — daily quota exhausted
    ├── PlanLimitationError — endpoint not available on current plan
    └── ParseError          — pydantic validation failed on response
"""

from __future__ import annotations


class APIFootballError(Exception):
    """Base exception for all API-Football errors."""


class UpstreamError(APIFootballError):
    """The upstream API returned a 5xx status or a network error occurred."""

    def __init__(self, status_code: int | None = None, detail: str = "") -> None:
        self.status_code = status_code
        super().__init__(detail or f"upstream error (HTTP {status_code})")


class RateLimitError(APIFootballError):
    """Per-minute request rate limit exceeded."""

    def __init__(self, retry_after: int | None = None) -> None:
        self.retry_after = retry_after
        msg = "rate limit exceeded"
        if retry_after is not None:
            msg += f" (retry after {retry_after}s)"
        super().__init__(msg)


class QuotaExhaustedError(APIFootballError):
    """Daily request quota exhausted."""


class PlanLimitationError(APIFootballError):
    """Endpoint or feature not available on the current subscription plan."""


class ParseError(APIFootballError):
    """Pydantic validation failed when parsing an API-Football response."""

    def __init__(self, detail: str = "", raw: object = None) -> None:
        self.raw = raw
        super().__init__(detail or "failed to parse API-Football response")
