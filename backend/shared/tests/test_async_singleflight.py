"""Tests for AsyncSingleflight deduplication."""

from __future__ import annotations

import asyncio

import pytest

from backend.shared.async_singleflight import AsyncSingleflight


async def test_dedupes_concurrent_calls() -> None:
    """Five concurrent callers for the same key → factory called once."""
    sf = AsyncSingleflight()
    call_count = 0

    async def slow_factory() -> str:
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.05)
        return "result"

    results = await asyncio.gather(
        *[sf.call("k1", slow_factory) for _ in range(5)]
    )

    assert call_count == 1
    assert results == ["result"] * 5


async def test_different_keys_run_in_parallel() -> None:
    """Three different keys → all three factories called."""
    sf = AsyncSingleflight()
    called_keys: list[str] = []

    async def factory(key: str) -> str:
        called_keys.append(key)
        await asyncio.sleep(0.01)
        return f"val-{key}"

    results = await asyncio.gather(
        sf.call("a", lambda: factory("a")),
        sf.call("b", lambda: factory("b")),
        sf.call("c", lambda: factory("c")),
    )

    assert sorted(called_keys) == ["a", "b", "c"]
    assert sorted(results) == ["val-a", "val-b", "val-c"]


async def test_leader_cancellation_does_not_cancel_waiters() -> None:
    """If the leader task is cancelled, waiters should receive a non-cancellation
    exception so the next call retries cleanly — they should NOT be cancelled
    themselves, since they didn't request cancellation."""
    sf = AsyncSingleflight()
    factory_started = asyncio.Event()

    async def slow_factory() -> str:
        factory_started.set()
        await asyncio.sleep(10)  # will be cancelled
        return "never"

    # Leader starts the flight
    leader_task = asyncio.create_task(sf.call("k", slow_factory))
    await factory_started.wait()

    # Waiter joins
    waiter_task = asyncio.create_task(sf.call("k", slow_factory))
    await asyncio.sleep(0.01)  # let waiter register

    # Cancel just the leader
    leader_task.cancel()

    # Leader should see CancelledError
    with pytest.raises(asyncio.CancelledError):
        await leader_task

    # Waiter should see a regular exception, NOT CancelledError
    with pytest.raises(Exception) as exc_info:
        await waiter_task
    assert not isinstance(exc_info.value, asyncio.CancelledError)

    # Next call to same key should start fresh (key was cleaned up)
    assert "k" not in sf._flights


async def test_exception_propagates_and_cleans_up() -> None:
    """Exception propagates to all waiters; subsequent call retries fresh."""
    sf = AsyncSingleflight()
    attempt = 0

    async def flaky_factory() -> str:
        nonlocal attempt
        attempt += 1
        await asyncio.sleep(0.02)
        if attempt == 1:
            raise ValueError("boom")
        return "recovered"

    # All concurrent callers see the exception.
    with pytest.raises(ValueError, match="boom"):
        await asyncio.gather(
            sf.call("k", flaky_factory),
            sf.call("k", flaky_factory),
        )

    # Key was cleaned up — next call retries fresh and succeeds.
    result = await sf.call("k", flaky_factory)
    assert result == "recovered"
    assert attempt == 2
