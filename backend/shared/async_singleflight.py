"""Async single-flight deduplication for concurrent cache lookups.

When multiple async callers request the same cache key simultaneously,
only one coroutine is executed; all waiters share the result (or
exception).  Once the flight completes the key is removed so the next
call starts fresh.

Usage::

    sf = AsyncSingleflight()

    async def fetch(key: str) -> dict:
        return await sf.call(key, lambda: expensive_http_call(key))
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any


class AsyncSingleflight:
    """Deduplicate concurrent async calls sharing the same string key."""

    def __init__(self) -> None:
        self._flights: dict[str, asyncio.Future[Any]] = {}

    async def call(
        self,
        key: str,
        coro_factory: Callable[[], Awaitable[Any]],
    ) -> Any:
        """Return the result for *key*, deduplicating concurrent callers.

        Parameters
        ----------
        key:
            Cache / request key used for deduplication.
        coro_factory:
            Zero-arg callable that returns an awaitable.  Invoked **only**
            when no in-flight request exists for *key*.

        Returns
        -------
        The value produced by *coro_factory*, shared across all concurrent
        callers for the same *key*.

        Raises
        ------
        Any exception raised by *coro_factory* is propagated to **all**
        waiting callers, and the key is cleaned up so the next call
        retries fresh.
        """
        loop = asyncio.get_running_loop()

        if key in self._flights:
            return await self._flights[key]

        future: asyncio.Future[Any] = loop.create_future()
        self._flights[key] = future

        try:
            result = await coro_factory()
        except asyncio.CancelledError:
            # Leader was cancelled.  Waiters should not inherit cancellation —
            # give them a generic RuntimeError so they kick off a fresh flight
            # on retry.
            if not future.done():
                future.set_exception(RuntimeError("singleflight leader cancelled"))
            raise
        except Exception as exc:
            future.set_exception(exc)
            raise
        else:
            future.set_result(result)
            return result
        finally:
            self._flights.pop(key, None)
