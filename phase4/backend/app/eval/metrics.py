"""Information-retrieval metrics used by the eval harness.

Standard textbook formulations — kept hand-rolled so the ranking-quality
test doesn't depend on scikit-learn just to compute three numbers. Each
function is pure (no I/O) and accepts iterables, which keeps callers
flexible: pass query results in any container.
"""
from __future__ import annotations

import math
from collections.abc import Sequence


def dcg(relevances: Sequence[float], *, k: int | None = None) -> float:
    """Discounted Cumulative Gain.

    Standard formulation:  sum_{i=1..k} rel_i / log2(i + 1).
    Position 1 has weight 1, position 2 has weight 1/log2(3) ≈ 0.63, etc.
    """
    cutoff = k if k is not None else len(relevances)
    score = 0.0
    for i, rel in enumerate(relevances[:cutoff], start=1):
        score += rel / math.log2(i + 1)
    return score


def ndcg(relevances: Sequence[float], *, k: int | None = None) -> float:
    """Normalised DCG. Returns 0.0 when no relevant docs exist.

    Normalises by the DCG of the *ideal* ranking (relevances sorted
    descending), which puts the score on a [0, 1] scale comparable across
    queries with different label distributions.
    """
    ideal = sorted(relevances, reverse=True)
    ideal_dcg = dcg(ideal, k=k)
    if ideal_dcg == 0:
        return 0.0
    return dcg(relevances, k=k) / ideal_dcg


def precision_at_k(relevances: Sequence[float], *, k: int) -> float:
    """Fraction of the top-k results with non-zero relevance."""
    if k <= 0:
        return 0.0
    top = relevances[:k]
    if not top:
        return 0.0
    relevant = sum(1 for rel in top if rel > 0)
    return relevant / min(k, len(top))
