"""Pluggable cache layer.

Phase 4 introduces a hot-query cache so the API can serve identical search
requests without rebuilding embeddings, scoring, and grouping every time.

The interface stays narrow on purpose — `get`, `set`, `invalidate`,
`clear` — so swapping `memory` for `redis` is a config flag rather than a
code change. Anything richer (tags, namespaces, batch ops) belongs in a
later phase.
"""
from app.cache.base import Cache, CacheEntry
from app.cache.factory import (
    build_search_cache_key,
    get_cache,
    reset_cache_for_tests,
)

__all__ = [
    "Cache",
    "CacheEntry",
    "build_search_cache_key",
    "get_cache",
    "reset_cache_for_tests",
]
