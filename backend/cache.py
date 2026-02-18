import json
import threading
import time
from typing import Any, Callable, Optional

try:
    import redis
except Exception:  # pragma: no cover - optional dependency
    redis = None

from backend.config import CACHE_ENABLED, CACHE_NAMESPACE, CACHE_VERSION, REDIS_URL


def _now() -> float:
    return time.time()


class _MemoryCache:
    def __init__(self) -> None:
        self._data: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            item = self._data.get(key)
            if not item:
                return None
            expires_at, value = item
            if expires_at and expires_at < _now():
                self._data.pop(key, None)
                return None
            return value

    def set(self, key: str, value: Any, ttl: int) -> None:
        expires_at = _now() + ttl if ttl else 0
        with self._lock:
            self._data[key] = (expires_at, value)

    def delete(self, key: str) -> None:
        with self._lock:
            self._data.pop(key, None)


class CacheClient:
    def __init__(self) -> None:
        self._enabled = CACHE_ENABLED
        self._mem = _MemoryCache()
        self._redis = None
        if self._enabled and REDIS_URL and redis:
            try:
                self._redis = redis.Redis.from_url(REDIS_URL, decode_responses=True)
                self._redis.ping()
            except Exception:
                self._redis = None
        self._locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    def _namespaced(self, key: str) -> str:
        return f"{CACHE_NAMESPACE}:{CACHE_VERSION}:{key}"

    def get(self, key: str) -> Optional[Any]:
        if not self._enabled:
            return None
        full_key = self._namespaced(key)
        if self._redis:
            raw = self._redis.get(full_key)
            return json.loads(raw) if raw is not None else None
        return self._mem.get(full_key)

    def set(self, key: str, value: Any, ttl: int) -> None:
        if not self._enabled:
            return
        full_key = self._namespaced(key)
        if self._redis:
            payload = json.dumps(value)
            self._redis.set(full_key, payload, ex=ttl)
            return
        self._mem.set(full_key, value, ttl)

    def delete(self, key: str) -> None:
        if not self._enabled:
            return
        full_key = self._namespaced(key)
        if self._redis:
            self._redis.delete(full_key)
            return
        self._mem.delete(full_key)

    def get_or_set(self, key: str, ttl: int, loader: Callable[[], Any]) -> Any:
        cached = self.get(key)
        if cached is not None:
            return cached
        value = loader()
        self.set(key, value, ttl)
        return value

    def with_singleflight_lock(self, key: str) -> threading.Lock:
        with self._locks_guard:
            if key not in self._locks:
                self._locks[key] = threading.Lock()
            return self._locks[key]

    def stale_while_revalidate(self, key: str, ttl: int, stale_ttl: int, loader: Callable[[], Any]) -> Any:
        cached = self.get(key)
        if cached is not None:
            return cached
        lock = self.with_singleflight_lock(key)
        with lock:
            cached = self.get(key)
            if cached is not None:
                return cached
            value = loader()
            self.set(key, value, ttl + stale_ttl)
            return value


cache = CacheClient()
