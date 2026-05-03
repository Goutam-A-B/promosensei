"""Redis-backed cache.

Optional — only loaded when `CACHE_PROVIDER=redis`. We pickle values
because the cache holds rich Python objects (Pydantic models embedded in
SearchResponse). Pickle is fine here because keys and values never leave
the trust boundary of our own services; never use this cache to ferry
data from untrusted sources.
"""
from __future__ import annotations

import logging
import pickle
from typing import Any

from app.cache.base import Cache

logger = logging.getLogger(__name__)


class RedisCache(Cache):
    def __init__(self, *, url: str) -> None:
        try:
            import redis  # type: ignore
        except ImportError as exc:  # pragma: no cover — exercised only when chosen
            raise RuntimeError(
                "redis package not installed. `pip install redis` or set CACHE_PROVIDER=memory."
            ) from exc
        self._client = redis.Redis.from_url(url)
        self._hits = 0
        self._misses = 0
        # Redis tracks its own evictions via `INFO`; we only count our writes.
        self._evictions = 0

    def get(self, key: str) -> Any | None:
        raw = self._client.get(key)
        if raw is None:
            self._misses += 1
            return None
        try:
            value = pickle.loads(raw)
        except Exception:
            logger.exception("Failed to unpickle cache value for key=%s", key)
            self._client.delete(key)
            self._misses += 1
            return None
        self._hits += 1
        return value

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        if ttl_seconds <= 0:
            return
        try:
            blob = pickle.dumps(value)
        except Exception:
            logger.exception("Failed to pickle cache value for key=%s", key)
            return
        self._client.set(key, blob, ex=ttl_seconds)

    def invalidate(self, key: str) -> bool:
        return bool(self._client.delete(key))

    def clear(self) -> None:
        # Note: this nukes the *entire* Redis db pointed at by the URL. If a
        # deployment co-locates the cache with other state, point the URL
        # at a dedicated db number (the `/0`, `/1`, ... suffix).
        self._client.flushdb()

    def stats(self) -> dict[str, int]:
        try:
            size = int(self._client.dbsize())
        except Exception:
            size = -1
        return {
            "hits": self._hits,
            "misses": self._misses,
            "evictions": self._evictions,
            "size": size,
        }
