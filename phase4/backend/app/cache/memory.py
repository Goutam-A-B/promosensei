"""In-process TTL + LRU cache.

Default backend. Two reasons to prefer this over Redis for the demo:

1. Zero ops cost — single-process FastAPI deployments don't need cross-
   process coherence, and the eval harness / tests can run without an
   external dependency.
2. The interface in `cache.base` is identical to Redis's, so flipping
   `CACHE_PROVIDER=redis` is the only thing required to scale out.

Eviction is plain LRU (oldest-accessed first) once `max_entries` is hit.
TTL expiry is checked lazily on read — we don't run a sweeper thread.
"""
from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Any, Callable

from app.cache.base import Cache, CacheEntry


class MemoryCache(Cache):
    def __init__(
        self,
        *,
        max_entries: int = 1024,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._max_entries = max_entries
        self._clock = clock
        self._store: OrderedDict[str, CacheEntry] = OrderedDict()
        # OrderedDict is not thread-safe under concurrent mutations even for
        # plain reads (move_to_end mutates the structure). FastAPI uses a
        # threadpool for sync routes, so we need the lock.
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    def get(self, key: str) -> Any | None:
        now = self._clock()
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self._misses += 1
                return None
            if entry.expires_at <= now:
                # Lazy expiration — drop the stale entry on the read path.
                del self._store[key]
                self._misses += 1
                return None
            # Touch for LRU.
            self._store.move_to_end(key)
            self._hits += 1
            return entry.value

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        if ttl_seconds <= 0:
            return
        expires = self._clock() + ttl_seconds
        with self._lock:
            if key in self._store:
                self._store.move_to_end(key)
            self._store[key] = CacheEntry(value=value, expires_at=expires)
            while len(self._store) > self._max_entries:
                self._store.popitem(last=False)
                self._evictions += 1

    def invalidate(self, key: str) -> bool:
        with self._lock:
            return self._store.pop(key, None) is not None

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {
                "hits": self._hits,
                "misses": self._misses,
                "evictions": self._evictions,
                "size": len(self._store),
            }
