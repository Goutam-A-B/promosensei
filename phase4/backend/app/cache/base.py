"""Cache interface shared by all backends.

The contract is deliberately small: read returns `None` for either misses
*or* expired entries (callers don't need to distinguish), and writes are
unconditional with a TTL. Backends own their own clock so tests can
inject a fake one.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class CacheEntry:
    value: Any
    expires_at: float  # epoch seconds


class Cache(ABC):
    """Backend-agnostic cache interface."""

    @abstractmethod
    def get(self, key: str) -> Any | None:
        """Return the cached value, or `None` if missing or expired."""

    @abstractmethod
    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        """Insert or overwrite a value with TTL."""

    @abstractmethod
    def invalidate(self, key: str) -> bool:
        """Remove one key. Returns True if the key existed."""

    @abstractmethod
    def clear(self) -> None:
        """Drop everything. Used by ingest jobs and by tests."""

    @abstractmethod
    def stats(self) -> dict[str, int]:
        """Return `{hits, misses, evictions, size}` for /metrics."""
