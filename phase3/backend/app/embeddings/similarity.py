"""Pure-Python vector helpers.

Phase 2 uses a Python-side scan over candidate vectors. That's fine for
tens of thousands of products. Phase 4 swaps in pgvector / Pinecone for
the larger catalog.
"""
from __future__ import annotations

import math
from collections.abc import Sequence


def l2_normalize(vec: Sequence[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0:
        return [0.0] * len(vec)
    return [v / norm for v in vec]


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity. Assumes inputs may or may not be normalized."""
    if len(a) != len(b):
        raise ValueError(f"Vector dim mismatch: {len(a)} vs {len(b)}")
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))
