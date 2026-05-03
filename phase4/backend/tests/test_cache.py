"""Cache layer: TTL semantics, LRU eviction, key stability."""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.cache import build_search_cache_key, get_cache, reset_cache_for_tests
from app.cache.factory import _NullCache
from app.cache.memory import MemoryCache


# ---- MemoryCache primitives ------------------------------------------------


def test_memory_cache_get_returns_value_within_ttl():
    clock = [0.0]
    cache = MemoryCache(max_entries=10, clock=lambda: clock[0])
    cache.set("k", "v", ttl_seconds=10)
    assert cache.get("k") == "v"


def test_memory_cache_expires_after_ttl():
    clock = [0.0]
    cache = MemoryCache(max_entries=10, clock=lambda: clock[0])
    cache.set("k", "v", ttl_seconds=10)
    clock[0] = 11.0
    assert cache.get("k") is None
    # Stats should reflect the miss.
    stats = cache.stats()
    assert stats["misses"] == 1
    assert stats["hits"] == 0


def test_memory_cache_lru_eviction_drops_oldest():
    cache = MemoryCache(max_entries=2)
    cache.set("a", 1, ttl_seconds=60)
    cache.set("b", 2, ttl_seconds=60)
    # Touch 'a' so 'b' becomes oldest.
    cache.get("a")
    cache.set("c", 3, ttl_seconds=60)
    assert cache.get("a") == 1
    assert cache.get("b") is None  # evicted
    assert cache.get("c") == 3
    assert cache.stats()["evictions"] == 1


def test_memory_cache_invalidate_removes_key():
    cache = MemoryCache()
    cache.set("k", "v", ttl_seconds=60)
    assert cache.invalidate("k") is True
    assert cache.invalidate("k") is False
    assert cache.get("k") is None


def test_memory_cache_clear_resets_storage_but_keeps_counters():
    cache = MemoryCache()
    cache.set("k", "v", ttl_seconds=60)
    cache.get("k")  # hit
    cache.clear()
    assert cache.get("k") is None
    # Counters are cumulative on purpose — stats are observability, not state.
    assert cache.stats()["size"] == 0


def test_memory_cache_zero_ttl_is_no_op():
    cache = MemoryCache()
    cache.set("k", "v", ttl_seconds=0)
    assert cache.get("k") is None


def test_memory_cache_overwrite_resets_expiry():
    clock = [0.0]
    cache = MemoryCache(clock=lambda: clock[0])
    cache.set("k", "v1", ttl_seconds=10)
    clock[0] = 5.0
    cache.set("k", "v2", ttl_seconds=10)
    clock[0] = 12.0  # past first TTL but not second
    assert cache.get("k") == "v2"


# ---- Null cache ------------------------------------------------------------


def test_null_cache_drops_writes_and_serves_misses():
    cache = _NullCache()
    cache.set("k", "v", ttl_seconds=60)
    assert cache.get("k") is None
    assert cache.invalidate("k") is False
    stats = cache.stats()
    assert stats == {"hits": 0, "misses": 0, "evictions": 0, "size": 0}


# ---- Provider factory ------------------------------------------------------


def test_get_cache_returns_singleton():
    reset_cache_for_tests()
    a = get_cache()
    b = get_cache()
    assert a is b


def test_reset_cache_for_tests_drops_singleton():
    reset_cache_for_tests()
    a = get_cache()
    reset_cache_for_tests()
    b = get_cache()
    assert a is not b


# ---- Cache key construction -----------------------------------------------


def test_search_cache_key_is_deterministic_across_runs():
    args = dict(
        raw_query="earbuds",
        mode="hybrid",
        min_price=None,
        max_price=Decimal("2000"),
        min_rating=Decimal("4.0"),
        platform=None,
        sort="relevance",
        page=1,
        page_size=24,
    )
    assert build_search_cache_key(**args) == build_search_cache_key(**args)


def test_search_cache_key_changes_on_meaningful_diff():
    base = dict(
        raw_query="earbuds",
        mode="hybrid",
        min_price=None,
        max_price=None,
        min_rating=None,
        platform=None,
        sort="relevance",
        page=1,
        page_size=24,
    )
    k0 = build_search_cache_key(**base)
    # Different query.
    assert build_search_cache_key(**{**base, "raw_query": "headphones"}) != k0
    # Different mode.
    assert build_search_cache_key(**{**base, "mode": "keyword"}) != k0
    # Different price filter.
    assert build_search_cache_key(**{**base, "max_price": Decimal("2000")}) != k0
    # Pagination.
    assert build_search_cache_key(**{**base, "page": 2}) != k0


def test_search_cache_key_normalises_query_whitespace_and_case():
    base = dict(
        mode="hybrid",
        min_price=None,
        max_price=None,
        min_rating=None,
        platform=None,
        sort="relevance",
        page=1,
        page_size=24,
    )
    assert build_search_cache_key(raw_query="Earbuds  ", **base) == build_search_cache_key(
        raw_query="earbuds", **base
    )


def test_search_cache_key_namespaced():
    args = dict(
        raw_query="x",
        mode="keyword",
        min_price=None,
        max_price=None,
        min_rating=None,
        platform=None,
        sort="relevance",
        page=1,
        page_size=24,
    )
    assert build_search_cache_key(**args).startswith("search:")
