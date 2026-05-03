"""Embedding provider protocol.

A provider knows how to turn text into a fixed-dimension vector. Phase 2 ships
three implementations:

- `HashingEmbeddingProvider`         — zero-dep default. Used by tests and
                                       suitable for tiny catalogs.
- `SentenceTransformersProvider`     — local MiniLM model. Recommended.
- `OpenAIEmbeddingProvider`          — text-embedding-3-small via API.

Providers are addressable by `model_id` so that vectors stored under one model
are never silently mixed with another (see edge case 5.2 in
docs/edge-cases.md).
"""
from __future__ import annotations

from typing import Protocol


class EmbeddingProvider(Protocol):
    @property
    def model_id(self) -> str:
        """Stable identifier stored alongside vectors. Format: '<provider>:<name>:<dim>'."""
        ...

    @property
    def dim(self) -> int:
        ...

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one L2-normalized vector per input text."""
        ...
