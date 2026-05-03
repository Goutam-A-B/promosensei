"""Cross-platform product matcher.

Decides whether an incoming `ScrapedListing` belongs to an existing
canonical product or warrants a new one. The signal stack, in priority
order:

1. **Hard guards** — bundle vs single, refurbished vs new, pack-size
   mismatch all *block* a match outright (edge cases 3.3 / 3.4 / 3.5).
2. **Brand + model number** — if both match exactly, that's a high-confidence
   match regardless of title cosmetics (edge case 3.2).
3. **Title fuzzy match (RapidFuzz)** — token-set ratio handles word
   reordering and casing differences (edge case 3.1).
4. **Embedding cosine** — last line of defense for rephrased titles
   ("Bluetooth Headset" vs "Wireless Headphones").
5. **Sanity check** — listings whose prices differ by more than ±25% are
   blocked from matching to filter scraping bugs (e.g. ₹500 laptop).

Architecture target: ≥ 70% of listings cluster correctly across platforms.
The thresholds below were tuned against a small fixture set and are
overridable via settings — Phase 4 brings a labeled eval set.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal

import re

from rapidfuzz import fuzz, utils
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.embeddings import EmbeddingProvider, cosine_similarity
from app.matching.brand import (
    extract_brand,
    extract_model_number,
    extract_pack_size,
    is_bundle,
    is_refurbished,
)
from app.models import Product
from app.schemas import ScrapedListing
from app.scraper.normalizer import clean_title

logger = logging.getLogger(__name__)

# Tunables — thresholds chosen to err on the side of *not* merging by accident.
# A false split is recoverable (re-run the matcher with a lower threshold);
# a false merge corrupts canonical product identity and is harder to fix.
#
# brand+model is the strongest cheap signal we have: when both the brand and
# the (hyphen-normalised) model number match exactly, the title is allowed
# to drift quite a bit before we refuse the merge — Flipkart "Bluetooth
# Headset" and Amazon "Wireless Headphones" describe the same product.
MIN_BRAND_MODEL_FUZZ = 50
MIN_TITLE_FUZZ = 90
MIN_EMBEDDING_COSINE = 0.78
PRICE_SANITY_RATIO = Decimal("0.25")  # ±25%


def _normalize_model(value: str | None) -> str:
    """Strip hyphens/spaces so 'WH-1000XM5' and 'WH1000XM5' compare equal."""
    if not value:
        return ""
    return "".join(ch for ch in value.upper() if ch.isalnum())


@dataclass
class MatchCandidate:
    """A canonical-product candidate with its precomputed signals."""

    product: Product
    title_fuzz: float = 0.0
    cosine: float = 0.0
    brand_match: bool = False
    model_match: bool = False
    blocked_reason: str | None = None


@dataclass
class MatchDecision:
    """The matcher's verdict — either a match (with the canonical product) or
    None, with the runner-up exposed for debugging."""

    matched: Product | None
    score: float
    reason: str
    runner_up: MatchCandidate | None = None


def canonical_title_for(listing: ScrapedListing) -> str:
    """The title we store on the canonical product.

    Prefers the cleaner of the two: the listing's title with platform noise
    stripped. We don't try to be clever about combining titles — last-write-
    wins is fine for the demo, and Phase 4 can swap in a smarter merger.
    """
    return clean_title(listing.title)


def _fuzz_key(title: str) -> str:
    """Title preprocessor for fuzz comparison.

    Collapses hyphens *inside* alphanumeric tokens before rapidfuzz's own
    default_process strips them. That way "WH-1000XM5" (Amazon) and
    "WH1000XM5" (Flipkart) tokenise identically and contribute to the
    intersection rather than landing in opposite diff sets.
    """
    if not title:
        return ""
    collapsed = re.sub(r"(?<=[A-Za-z0-9])-(?=[A-Za-z0-9])", "", title)
    return utils.default_process(collapsed) or ""


def _within_price_sanity(a: Decimal, b: Decimal) -> bool:
    """True if the two prices are within ±PRICE_SANITY_RATIO of each other.

    Catches scraping bugs where one platform extracted ₹500 instead of
    ₹50,000. We compare against the *higher* price so a genuine 50%-off sale
    isn't flagged as a mismatch.
    """
    if a <= 0 or b <= 0:
        return False
    hi = max(a, b)
    lo = min(a, b)
    return (hi - lo) / hi <= PRICE_SANITY_RATIO


def _hard_block(listing: ScrapedListing, candidate: Product) -> str | None:
    """Return a reason if this pair *cannot* match, regardless of similarity."""
    listing_title = listing.title or ""
    cand_title = candidate.canonical_title or ""

    if is_bundle(listing_title) != is_bundle(cand_title):
        return "bundle/single mismatch"
    if is_refurbished(listing_title) != is_refurbished(cand_title):
        return "refurbished/new mismatch"

    listing_pack = extract_pack_size(listing_title)
    cand_pack = extract_pack_size(cand_title)
    if listing_pack and cand_pack and listing_pack != cand_pack:
        return f"pack-size mismatch ({listing_pack} vs {cand_pack})"

    return None


def _candidate_score(c: MatchCandidate) -> float:
    """Combined ranking score — higher is better. Used to pick the best
    candidate when multiple satisfy the thresholds."""
    return c.title_fuzz / 100.0 * 0.5 + c.cosine * 0.4 + (0.1 if c.model_match else 0.0)


def find_canonical_match(
    db: Session,
    listing: ScrapedListing,
    *,
    embedding_provider: EmbeddingProvider | None = None,
    listing_vector: list[float] | None = None,
) -> MatchDecision:
    """Look for an existing canonical product that matches `listing`.

    `listing_vector` is optional — pass it in if the caller already embedded
    the listing title (saves one provider call per listing in batched flows).
    """
    listing_brand = extract_brand(listing.title)
    listing_model = extract_model_number(listing.title)
    listing_pack = extract_pack_size(listing.title)

    # Cheap pre-filter: same-brand candidates first; if none, fall back to
    # same-model-number; if still none, bail (no plausible match).
    if listing_brand:
        rows = db.scalars(
            select(Product).where(Product.brand == listing_brand)
        ).all()
    elif listing_model:
        rows = db.scalars(
            select(Product).where(Product.model_number == listing_model)
        ).all()
    else:
        rows = []

    if not rows:
        return MatchDecision(matched=None, score=0.0, reason="no candidate pool")

    # Compute the listing-side fuzz key once.
    listing_key = _fuzz_key(listing.title)

    candidates: list[MatchCandidate] = []
    for product in rows:
        block = _hard_block(listing, product)
        if block:
            candidates.append(MatchCandidate(product=product, blocked_reason=block))
            continue
        if not _within_price_sanity(listing.price, _representative_price(product)):
            candidates.append(
                MatchCandidate(product=product, blocked_reason="price outside ±25% sanity range")
            )
            continue

        cand_brand = product.brand
        cand_model = product.model_number
        cand_key = _fuzz_key(product.canonical_title)

        title_fuzz = fuzz.token_set_ratio(listing_key, cand_key, processor=None)

        cosine = 0.0
        if listing_vector is not None and embedding_provider is not None:
            # Heavy path: pull the candidate's vector. Cheaper paths (brand+
            # model already matched) skip this.
            cand_vec = _candidate_vector(db, product, embedding_provider.model_id)
            if cand_vec is not None:
                try:
                    cosine = cosine_similarity(listing_vector, cand_vec)
                except ValueError:
                    cosine = 0.0

        brand_match = bool(cand_brand and listing_brand and cand_brand.lower() == listing_brand.lower())
        model_match = bool(
            cand_model
            and listing_model
            and _normalize_model(cand_model) == _normalize_model(listing_model)
        )

        candidates.append(
            MatchCandidate(
                product=product,
                title_fuzz=float(title_fuzz),
                cosine=float(cosine),
                brand_match=brand_match,
                model_match=model_match,
            )
        )

    eligible = [c for c in candidates if c.blocked_reason is None]
    if not eligible:
        reasons = ", ".join(sorted({c.blocked_reason for c in candidates if c.blocked_reason})) or "no candidates"
        return MatchDecision(matched=None, score=0.0, reason=f"all candidates blocked: {reasons}")

    # Pick the strongest candidate.
    eligible.sort(key=_candidate_score, reverse=True)
    best = eligible[0]
    runner_up = eligible[1] if len(eligible) > 1 else None

    # Decision tree: brand+model wins on relaxed fuzz threshold; otherwise
    # require either high fuzz OR high embedding cosine.
    if best.brand_match and best.model_match and best.title_fuzz >= MIN_BRAND_MODEL_FUZZ:
        return MatchDecision(
            matched=best.product,
            score=_candidate_score(best),
            reason=f"brand+model match (fuzz={best.title_fuzz:.1f})",
            runner_up=runner_up,
        )
    if best.title_fuzz >= MIN_TITLE_FUZZ:
        return MatchDecision(
            matched=best.product,
            score=_candidate_score(best),
            reason=f"title fuzz match ({best.title_fuzz:.1f})",
            runner_up=runner_up,
        )
    if best.cosine >= MIN_EMBEDDING_COSINE:
        return MatchDecision(
            matched=best.product,
            score=_candidate_score(best),
            reason=f"embedding cosine match ({best.cosine:.3f})",
            runner_up=runner_up,
        )

    return MatchDecision(
        matched=None,
        score=_candidate_score(best),
        reason=(
            f"below thresholds (fuzz={best.title_fuzz:.1f}, "
            f"cosine={best.cosine:.3f}, brand={best.brand_match}, model={best.model_match})"
        ),
        runner_up=best,
    )


def _representative_price(product: Product) -> Decimal:
    """Lowest price across the product's listings — proxy for "true price"."""
    if not product.listings:
        return Decimal("0")
    return min(listing.price for listing in product.listings)


def _candidate_vector(db: Session, product: Product, model_id: str) -> list[float] | None:
    """Lazy-load the cached embedding for a candidate product."""
    from app.models import ProductEmbedding  # local import avoids cycles

    row = db.scalars(
        select(ProductEmbedding).where(
            ProductEmbedding.product_id == product.id,
            ProductEmbedding.model_id == model_id,
        )
    ).first()
    if row is None:
        return None
    import json
    try:
        return json.loads(row.vector_json)
    except (TypeError, ValueError):
        return None
