"""Tests for the hybrid ranker.

Covers edge cases 6.1 (deterministic tiebreak), 6.2 (Bayesian smoothing for
missing ratings), 6.3 (winsorized discount).
"""
from decimal import Decimal

from app.ranking import Candidate, rank_candidates


def _cand(pid: int, sim: float, rating: float | None = None, discount: float | None = None) -> Candidate:
    return Candidate(
        product_id=pid,
        similarity=sim,
        rating=Decimal(str(rating)) if rating is not None else None,
        discount=Decimal(str(discount)) if discount is not None else None,
    )


def test_returns_empty_for_no_candidates():
    assert rank_candidates([]) == []


def test_higher_similarity_wins_when_other_signals_equal():
    cands = [
        _cand(1, sim=0.4, rating=4.0, discount=20.0),
        _cand(2, sim=0.9, rating=4.0, discount=20.0),
    ]
    scored = rank_candidates(cands)
    assert scored[0].product_id == 2
    assert scored[1].product_id == 1


def test_tied_scores_break_by_product_id():
    cands = [
        _cand(7, sim=0.5, rating=4.0, discount=20.0),
        _cand(3, sim=0.5, rating=4.0, discount=20.0),
        _cand(5, sim=0.5, rating=4.0, discount=20.0),
    ]
    scored = rank_candidates(cands)
    assert [s.product_id for s in scored] == [3, 5, 7]


def test_missing_rating_gets_smoothed_not_zero():
    """Edge case 6.2: a rating-less product shouldn't be unfairly buried."""
    rated = _cand(1, sim=0.5, rating=4.0, discount=20.0)
    unrated = _cand(2, sim=0.5, rating=None, discount=20.0)
    scored = {s.product_id: s for s in rank_candidates([rated, unrated])}
    # The unrated product gets a non-zero rating component (priored toward 3.5 / 5).
    assert scored[2].breakdown["rating"] > 0.5
    # And it should not score zero just because rating is None.
    assert scored[2].score > 0.4


def test_winsorize_caps_outlier_discount():
    """Edge case 6.3: a 99% outlier shouldn't dominate the discount signal.

    With winsorization at the 95th percentile, the 99% outlier collapses to
    the cap (~30%), so it scores no higher than products with the second-
    highest discount. Without winsorization it would consume nearly the
    full normalized range and crush everyone else's contribution to ~0.
    """
    cands = [_cand(i, sim=0.5, rating=4.0, discount=10.0 + i) for i in range(1, 20)]
    cands.append(_cand(99, sim=0.5, rating=4.0, discount=99.0))
    scored = {s.product_id: s for s in rank_candidates(cands)}

    # The outlier is capped at the 95th-percentile value, which equals the
    # discount of the highest non-outlier product. So the outlier and the
    # highest legitimate discount end up tied on the discount signal.
    outlier_disc = scored[99].breakdown["discount"]
    top_legit_disc = scored[19].breakdown["discount"]
    assert outlier_disc == top_legit_disc

    # And the spread between the lowest and highest legitimate products is
    # preserved — i.e. the outlier didn't compress everyone else into noise.
    bottom_disc = scored[1].breakdown["discount"]
    assert top_legit_disc - bottom_disc > 0.5


def test_weights_can_be_overridden():
    cands = [
        _cand(1, sim=0.9, rating=1.0, discount=0.0),
        _cand(2, sim=0.1, rating=5.0, discount=80.0),
    ]
    # Default weights — similarity dominates.
    default = rank_candidates(cands)
    assert default[0].product_id == 1
    # Flip the weights — now discount + rating dominate.
    flipped = rank_candidates(cands, w_similarity=0.0, w_discount=0.5, w_rating=0.5)
    assert flipped[0].product_id == 2


def test_similarity_clamped_to_unit_interval():
    # Negative cosine values are real (anti-correlated vectors).
    cands = [_cand(1, sim=-0.3), _cand(2, sim=1.3)]
    scored = rank_candidates(cands)
    sims = {s.product_id: s.similarity for s in scored}
    assert sims[1] == 0.0
    assert sims[2] == 1.0
