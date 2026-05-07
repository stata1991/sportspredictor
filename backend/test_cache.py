"""Tests for backend.cache — LRU eviction, TTL expiry, singleflight."""

from __future__ import annotations

import threading
import time
from unittest.mock import patch

import pytest

from backend.cache import _MemoryCache, CacheClient


class TestMemoryCacheLRU:
    """LRU eviction in _MemoryCache."""

    def test_evicts_oldest_entry_when_full(self) -> None:
        mc = _MemoryCache(max_size=3)
        mc.set("a", 1, ttl=60)
        mc.set("b", 2, ttl=60)
        mc.set("c", 3, ttl=60)
        mc.set("d", 4, ttl=60)  # should evict "a"

        assert mc.get("a") is None
        assert mc.get("b") == 2
        assert mc.get("d") == 4

    def test_get_promotes_entry(self) -> None:
        mc = _MemoryCache(max_size=3)
        mc.set("a", 1, ttl=60)
        mc.set("b", 2, ttl=60)
        mc.set("c", 3, ttl=60)

        mc.get("a")  # promote "a" → most-recently-used
        mc.set("d", 4, ttl=60)  # should evict "b" (now oldest)

        assert mc.get("a") == 1
        assert mc.get("b") is None
        assert mc.get("d") == 4

    def test_set_existing_key_promotes(self) -> None:
        mc = _MemoryCache(max_size=3)
        mc.set("a", 1, ttl=60)
        mc.set("b", 2, ttl=60)
        mc.set("c", 3, ttl=60)

        mc.set("a", 10, ttl=60)  # update "a" → promote
        mc.set("d", 4, ttl=60)   # should evict "b"

        assert mc.get("a") == 10
        assert mc.get("b") is None

    def test_max_size_one(self) -> None:
        mc = _MemoryCache(max_size=1)
        mc.set("a", 1, ttl=60)
        mc.set("b", 2, ttl=60)

        assert mc.get("a") is None
        assert mc.get("b") == 2


class TestMemoryCacheTTL:
    """TTL expiry in _MemoryCache."""

    def test_expired_entry_returns_none(self) -> None:
        mc = _MemoryCache(max_size=100)
        mc.set("k", "v", ttl=1)

        with patch("backend.cache._now", return_value=time.time() + 2):
            assert mc.get("k") is None

    def test_non_expired_entry_returns_value(self) -> None:
        mc = _MemoryCache(max_size=100)
        mc.set("k", "v", ttl=60)
        assert mc.get("k") == "v"

    def test_zero_ttl_never_expires(self) -> None:
        mc = _MemoryCache(max_size=100)
        mc.set("k", "v", ttl=0)

        with patch("backend.cache._now", return_value=time.time() + 999999):
            assert mc.get("k") == "v"


class TestMemoryCacheDelete:
    def test_delete_removes_entry(self) -> None:
        mc = _MemoryCache(max_size=100)
        mc.set("k", "v", ttl=60)
        mc.delete("k")
        assert mc.get("k") is None

    def test_delete_nonexistent_key_is_noop(self) -> None:
        mc = _MemoryCache(max_size=100)
        mc.delete("nope")  # should not raise


class TestCacheClientSingleflight:
    """Singleflight deduplication via stale_while_revalidate."""

    def test_concurrent_calls_deduplicate(self) -> None:
        call_count = 0

        def slow_loader() -> str:
            nonlocal call_count
            call_count += 1
            time.sleep(0.1)
            return "result"

        client = CacheClient()
        results: list[str] = []

        def worker() -> None:
            r = client.stale_while_revalidate("sf-key", ttl=60, stale_ttl=0, loader=slow_loader)
            results.append(r)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert all(r == "result" for r in results)
        assert call_count == 1
