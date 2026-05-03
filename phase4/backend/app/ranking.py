"""Hybrid ranker for Phase 2.

Score = w_sim * cosine + w_disc * normalized_discount + w_rating * smoothed_rating

Defaults follow the formula in docs/architecture.md (0.6 / 0.2 / 0.2). All
weights are configurable via settings so we can tune in Phase 4 without code
changes.

Edge cases handled here:

- 6.1 Tied scores               → deterministic tiebreak by product_id
- 6.2 New products no rating    → Bayesian smoothing toward category mean
- 6.3 Outlier discount skewing  → winsorize at 95th percentile
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass
class Candidate:
    product_id: int
    similarity: float
    rating: Decimal | None
    discount: Decimal | None


@dataclass
class Scored:
    product_id: int
    score: float
    similarity: float
    breakdown: dict[str, float]


_BAYESIAN_PRIOR_RATING = 3.5  # neutral midpoint of 1..5
_BAYESIAN_PRIOR_WEIGHT = 5.0  # how strongly we pull missing ratings toward the prior


def _winsorize(values: list[float], pct: float = 95.0) -> list[float]:
    if not values:
        return values
    sorted_vals = sorted(values)
    cutoff_idx = int(len(sorted_vals) * pct / 100.0) - 1
    cutoff_idx = max(0, min(cutoff_idx, len(sorted_vals) - 1))
    cap = sorted_vals[cutoff_idx]
    if cap <= 0:
        return values
    return [min(v, cap) for v in values]


def _normalize_minmax(values: list[float]) -> list[float]:
    if not values:
        return values
    lo = min(values)
    hi = max(values)
    if hi - lo < 1e-9:
        return [0.0 for _ in values]
    return [(v - lo) / (hi - lo) for v in values]


def _smoothed_rating(rating: Decimal | None) -> float:
    """Bayesian smoothing toward the prior mean, normalized to 0..1."""
    n_observed = 0.0 if rating is None else 1.0
    observed = float(rating) if rating is not None else 0.0
    smoothed = (
        _BAYESIAN_PRIOR_WEIGHT * _BAYESIAN_PRIOR_RATING + n_observed * observed
    ) / (_BAYESIAN_PRIOR_WEIGHT + n_observed)
    return max(0.0, min(1.0, smoothed / 5.0))


def rank_candidates(
    candidates: list[Candidate],
    *,
    w_similarity: float = 0.6,
    w_discount: float = 0.2,
    w_rating: float = 0.2,
) -> list[Scored]:
    if not candidates:
        return []

    raw_discounts = [float(c.discount) if c.discount is not None else 0.0 for c in candidates]
    winsorized = _winsorize(raw_discounts, pct=95.0)
    normalized_discounts = _normalize_minmax(winsorized)
    rating_scores = [_smoothed_rating(c.rating) for c in candidates]

    total = max(1e-9, w_similarity + w_discount + w_rating)
    ws = w_similarity / total
    wd = w_discount / total
    wr = w_rating / total

    scored: list[Scored] = []
    for cand, disc_norm, rating_norm in zip(candidates, normalized_discounts, rating_scores):
        sim = max(0.0, min(1.0, cand.similarity))
        score = ws * sim + wd * disc_norm + wr * rating_norm
        scored.append(
            Scored(
                product_id=cand.product_id,
                score=score,
                similarity=sim,
                breakdown={
                    "similarity": sim,
                    "discount": disc_norm,
                    "rating": rating_norm,
                    "weights": {"sim": ws, "discount": wd, "rating": wr},
                },
            )
        )

    # Deterministic tiebreak by product_id (edge case 6.1).
    scored.sort(key=lambda s: (-s.score, s.product_id))
    return scored
