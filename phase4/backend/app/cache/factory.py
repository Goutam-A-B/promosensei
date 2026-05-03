"""Provider selection + cache key construction.

Two responsibilities live here on purpose: anything that *touches* the
cache should import from one place, and the key builder is the part that
most often needs to be inspected when a stale-result bug shows up.
"""
from __future__ import annotations

import hashlib
import json
import logging
from decimal import Decimal
from typing import Any

from app.cache.base import Cache
from app.cache.memory import MemoryCache
from app.config import get_settings

logger = logging.getLogger(__name__)

_cache: Cache | None = None


class _NullCache(Cache):
    """Cache that drops every write and serves every read as a miss.

    Used when `cache_provider="none"` and by tests that want to assert the
    DB path runs every time.
    """

    def get(self, key: str) -> Any | None:  # noqa: D401
        return None

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        return None

    def invalidate(self, key: str) -> bool:
        return False

    def clear(self) -> None:
        return None

    def stats(self) -> dict[str, int]:
        return {"hits": 0, "misses": 0, "evictions": 0, "size": 0}


def get_cache() -> Cache:
    """Lazy-built process-wide cache singleton."""
    global _cache
    if _cache is not None:
        return _cache
    settings = get_settings()
    provider = (settings.cache_provider or "memory").lower()
    if provider == "memory":
        _cache = MemoryCache(max_entries=settings.cache_max_entries)
    elif provider == "redis":
        from app.cache.redis_provider import RedisCache

        _cache = RedisCache(url=settings.cache_redis_url)
    elif provider == "none":
        _cache = _NullCache()
    else:
        logger.warning("Unknown cache_provider=%s — falling back to memory", provider)
        _cache = MemoryCache(max_entries=settings.cache_max_entries)
    return _cache


def reset_cache_for_tests() -> None:
    """Drop the singleton so a fresh cache is built on next access.

    Tests that change `cache_provider` between cases need this — without
    it the first instance leaks across test boundaries.
    """
    global _cache
    _cache = None


# ---- Key construction ------------------------------------------------------


def _coerce(value: Any) -> Any:
    """Make values JSON-serializable so the key is stable across Python
    builds (Decimal/None/etc. all collapse to their stringified form)."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return str(value)
    return value


def build_search_cache_key(
    *,
    raw_query: str,
    mode: str,
    min_price: Decimal | None,
    max_price: Decimal | None,
    min_rating: Decimal | None,
    platform: str | None,
    sort: str,
    page: int,
    page_size: int,
) -> str:
    """Hash the full request shape into a stable cache key.

    Two requests collide iff every observable parameter matches. We hash
    rather than concatenate so the key length stays bounded regardless of
    query text and so logs don't leak full user queries by default.
    """
    payload = {
        "q": (raw_query or "").strip().lower(),
        "mode": mode,
        "min_price": _coerce(min_price),
        "max_price": _coerce(max_price),
        "min_rating": _coerce(min_rating),
        "platform": platform,
        "sort": sort,
        "page": page,
        "page_size": page_size,
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(blob.encode("utf-8")).hexdigest()[:24]
    return f"search:{digest}"
