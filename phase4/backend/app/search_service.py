"""Search orchestration over the Phase 3 canonical-product graph.

The query unit is a `Product` (canonical), not a `Listing`. Every result has
the product's offers across platforms attached so the UI can show a single
card with a per-platform price ladder.

Filters with a price/rating/platform shape are applied at the *listing*
level: a product is included if **any** of its listings satisfies the
filter. The result then surfaces only the matching listings. This matches
the user mental model — "show me earbuds under ₹2000" should find a product
that's overpriced on Amazon but cheap on Flipkart.

Three modes (unchanged from Phase 2):

- `keyword`  — SQL ILIKE against canonical_title, brand, and listing.raw_title
- `semantic` — embed the query, scan vectors, re-rank
- `hybrid`   — union of both, re-ranked together

Both vector-using modes degrade to keyword search if the index is empty
(edge case 5.1) or no candidates pass the filters.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.embeddings import get_embedding_provider
from app.embeddings.similarity import cosine_similarity
from app.models import Listing, Product, ProductEmbedding
from app.query_parser import ParsedQuery, parse_query
from app.ranking import Candidate, rank_candidates

logger = logging.getLogger(__name__)

SearchMode = Literal["keyword", "semantic", "hybrid"]


@dataclass
class SearchHit:
    """One canonical product plus the listings that survived filtering."""

    product: Product
    matching_listings: list[Listing]
    score: float
    similarity: float


@dataclass
class SearchResult:
    query: str
    parsed_residual: str
    mode: SearchMode
    effective_mode: SearchMode  # what actually ran (e.g. fell back to keyword)
    notes: list[str]
    total: int
    page: int
    page_size: int
    hits: list[SearchHit] = field(default_factory=list)


# ---- Filtering ------------------------------------------------------------


def _listing_matches(
    listing: Listing,
    *,
    min_price: Decimal | None,
    max_price: Decimal | None,
    min_rating: Decimal | None,
    platform: str | None,
) -> bool:
    """True if this listing satisfies the structured filters."""
    if min_price is not None and listing.price < min_price:
        return False
    if max_price is not None and listing.price > max_price:
        return False
    if min_rating is not None:
        # Treat unrated listings as failing min_rating — tighter, but the user
        # asked for a minimum, not "anything that might qualify".
        if listing.rating is None or listing.rating < min_rating:
            return False
    if platform and listing.platform != platform:
        return False
    return True


def _filter_listings(
    product: Product,
    *,
    min_price: Decimal | None,
    max_price: Decimal | None,
    min_rating: Decimal | None,
    platform: str | None,
) -> list[Listing]:
    return [
        l
        for l in product.listings
        if _listing_matches(
            l,
            min_price=min_price,
            max_price=max_price,
            min_rating=min_rating,
            platform=platform,
        )
    ]


def _best_listing(listings: list[Listing]) -> Listing | None:
    """Cheapest listing — that's what we sort/group by."""
    if not listings:
        return None
    return min(listings, key=lambda l: l.price)


def _max_discount(listings: list[Listing]) -> Decimal | None:
    discounts = [l.discount for l in listings if l.discount is not None]
    return max(discounts) if discounts else None


def _max_rating(listings: list[Listing]) -> Decimal | None:
    ratings = [l.rating for l in listings if l.rating is not None]
    return max(ratings) if ratings else None


# ---- Keyword search -------------------------------------------------------


def _keyword_candidates(
    db: Session,
    *,
    text: str,
    platform: str | None,
) -> list[Product]:
    """Return Products whose canonical title, brand, or any listing's
    raw title matches all whitespace-separated tokens (AND semantics).

    Platform filter pushes into the listing join so we don't load products
    that have no listings on the requested platform at all.
    """
    stmt: Select = select(Product).options(selectinload(Product.listings))

    if platform:
        # Only consider products that have at least one listing on the platform.
        stmt = stmt.join(Listing, Listing.product_id == Product.id).where(
            Listing.platform == platform
        ).distinct()

    tokens = [t for t in (text or "").split() if t]
    for token in tokens:
        like = f"%{token}%"
        # Match against canonical title OR brand OR any listing's raw title.
        listing_match = (
            select(Listing.id)
            .where(Listing.product_id == Product.id, Listing.raw_title.ilike(like))
            .exists()
        )
        stmt = stmt.where(
            or_(
                Product.canonical_title.ilike(like),
                Product.brand.ilike(like),
                listing_match,
            )
        )

    return list(db.scalars(stmt).all())


# ---- Semantic search ------------------------------------------------------


def _index_size(db: Session, model_id: str) -> int:
    return int(
        db.scalar(
            select(func.count(ProductEmbedding.id)).where(ProductEmbedding.model_id == model_id)
        )
        or 0
    )


def _semantic_candidates(
    db: Session,
    *,
    query_vector: list[float],
    model_id: str,
    top_k: int,
    min_similarity: float = 0.0,
) -> list[tuple[Product, float]]:
    """Score every embedded product by cosine similarity, return top_k.

    Filtering happens *after* this step, on the listings — that way a
    product with one cheap listing on Flipkart still surfaces even if its
    Amazon listing is over the user's max price.

    `min_similarity` drops candidates whose cosine is below the floor.
    With a weak embedder (hashing) every product gets a non-zero score
    from incidental trigram overlap; without a floor, queries with no
    real match return an arbitrary list ranked by discount/rating, which
    is misleading. The floor turns "garbage in" into "no results".
    """
    stmt = (
        select(Product, ProductEmbedding.vector_json)
        .join(ProductEmbedding, ProductEmbedding.product_id == Product.id)
        .where(ProductEmbedding.model_id == model_id)
        .options(selectinload(Product.listings))
    )
    rows = db.execute(stmt).all()

    scored: list[tuple[Product, float]] = []
    for product, vector_json in rows:
        try:
            vector = json.loads(vector_json)
        except (TypeError, ValueError):
            continue
        try:
            sim = cosine_similarity(query_vector, vector)
        except ValueError:
            # Dimension mismatch shouldn't happen for the same model_id.
            continue
        if sim < min_similarity:
            continue
        scored.append((product, sim))

    scored.sort(key=lambda x: (-x[1], x[0].id))
    return scored[:top_k]


# ---- Public entry point ---------------------------------------------------


def search(
    db: Session,
    *,
    raw_query: str,
    mode: SearchMode | None = None,
    min_price: Decimal | None = None,
    max_price: Decimal | None = None,
    min_rating: Decimal | None = None,
    platform: str | None = None,
    sort: str = "relevance",
    page: int = 1,
    page_size: int = 24,
) -> SearchResult:
    settings = get_settings()
    requested_mode: SearchMode = mode or settings.search_default_mode  # type: ignore[assignment]

    parsed: ParsedQuery = parse_query(raw_query)
    notes = list(parsed.notes)

    # Filters from explicit args take precedence — only fill in from parsed query
    # when the caller didn't already specify the field.
    if min_price is None and parsed.min_price is not None:
        min_price = parsed.min_price
    if max_price is None and parsed.max_price is not None:
        max_price = parsed.max_price
    if min_rating is None and parsed.min_rating is not None:
        min_rating = parsed.min_rating

    effective_text = parsed.residual or raw_query.strip()
    is_empty_query = not effective_text

    # --- Empty query: curated trending deals (edge case 4.1) ---------------
    if is_empty_query:
        notes.append("empty query → curated trending deals")
        candidates = _keyword_candidates(db, text="", platform=platform)
        return _finalize(
            db=db,
            products_with_sim=[(p, 0.0) for p in candidates],
            min_price=min_price,
            max_price=max_price,
            min_rating=min_rating,
            platform=platform,
            sort="discount_desc" if sort == "relevance" else sort,
            page=page,
            page_size=page_size,
            raw_query=raw_query,
            parsed_residual=parsed.residual,
            mode=requested_mode,
            effective_mode="keyword",
            notes=notes,
            rank_with_similarity=False,
        )

    # --- Keyword mode ------------------------------------------------------
    if requested_mode == "keyword":
        candidates = _keyword_candidates(db, text=effective_text, platform=platform)
        return _finalize(
            db=db,
            products_with_sim=[(p, 0.0) for p in candidates],
            min_price=min_price,
            max_price=max_price,
            min_rating=min_rating,
            platform=platform,
            sort=sort,
            page=page,
            page_size=page_size,
            raw_query=raw_query,
            parsed_residual=parsed.residual,
            mode="keyword",
            effective_mode="keyword",
            notes=notes,
            rank_with_similarity=False,
        )

    # --- Semantic / hybrid -------------------------------------------------
    provider = get_embedding_provider()
    if _index_size(db, provider.model_id) == 0:
        notes.append("vector index empty — falling back to keyword search")
        candidates = _keyword_candidates(db, text=effective_text, platform=platform)
        return _finalize(
            db=db,
            products_with_sim=[(p, 0.0) for p in candidates],
            min_price=min_price,
            max_price=max_price,
            min_rating=min_rating,
            platform=platform,
            sort=sort,
            page=page,
            page_size=page_size,
            raw_query=raw_query,
            parsed_residual=parsed.residual,
            mode=requested_mode,
            effective_mode="keyword",
            notes=notes,
            rank_with_similarity=False,
        )

    query_vector = provider.embed([effective_text])[0]
    semantic_hits = _semantic_candidates(
        db,
        query_vector=query_vector,
        model_id=provider.model_id,
        top_k=settings.search_top_k,
        min_similarity=settings.search_min_similarity,
    )

    sim_by_id: dict[int, float] = {p.id: sim for p, sim in semantic_hits}
    candidates_by_id: dict[int, Product] = {p.id: p for p, _ in semantic_hits}

    # Hybrid: union the semantic candidates with keyword matches so we don't
    # miss exact-phrase hits the embedding may have ranked below top_k.
    if requested_mode == "hybrid":
        for product in _keyword_candidates(db, text=effective_text, platform=platform):
            if product.id not in candidates_by_id:
                candidates_by_id[product.id] = product
                sim_by_id[product.id] = 0.0  # ranker still considers discount + rating

    if not candidates_by_id:
        notes.append("no semantic candidates — falling back to keyword")
        keyword_hits = _keyword_candidates(db, text=effective_text, platform=platform)
        return _finalize(
            db=db,
            products_with_sim=[(p, 0.0) for p in keyword_hits],
            min_price=min_price,
            max_price=max_price,
            min_rating=min_rating,
            platform=platform,
            sort=sort,
            page=page,
            page_size=page_size,
            raw_query=raw_query,
            parsed_residual=parsed.residual,
            mode=requested_mode,
            effective_mode="keyword",
            notes=notes,
            rank_with_similarity=False,
        )

    products_with_sim = [(p, sim_by_id.get(p.id, 0.0)) for p in candidates_by_id.values()]
    return _finalize(
        db=db,
        products_with_sim=products_with_sim,
        min_price=min_price,
        max_price=max_price,
        min_rating=min_rating,
        platform=platform,
        sort=sort,
        page=page,
        page_size=page_size,
        raw_query=raw_query,
        parsed_residual=parsed.residual,
        mode=requested_mode,
        effective_mode=requested_mode,
        notes=notes,
        rank_with_similarity=True,
    )


# ---- Finalize -------------------------------------------------------------


def _finalize(
    *,
    db: Session,
    products_with_sim: list[tuple[Product, float]],
    min_price: Decimal | None,
    max_price: Decimal | None,
    min_rating: Decimal | None,
    platform: str | None,
    sort: str,
    page: int,
    page_size: int,
    raw_query: str,
    parsed_residual: str,
    mode: SearchMode,
    effective_mode: SearchMode,
    notes: list[str],
    rank_with_similarity: bool,
) -> SearchResult:
    """Filter listings, drop empty groups, score, sort, paginate."""
    settings = get_settings()

    # Step 1: per-product, drop listings that don't pass the filters. If a
    # product has no surviving listings, drop the product itself.
    survivors: list[tuple[Product, list[Listing], float]] = []
    for product, sim in products_with_sim:
        # Defensive: triggers selectinload if it wasn't pre-loaded.
        listings = _filter_listings(
            product,
            min_price=min_price,
            max_price=max_price,
            min_rating=min_rating,
            platform=platform,
        )
        if not listings:
            continue
        survivors.append((product, listings, sim))

    if not survivors:
        return SearchResult(
            query=raw_query,
            parsed_residual=parsed_residual,
            mode=mode,
            effective_mode=effective_mode,
            notes=notes,
            total=0,
            page=page,
            page_size=page_size,
            hits=[],
        )

    # Step 2: rank — similarity + discount + rating, with discount/rating
    # taken from the *best* listing in the surviving set.
    cand_objs = [
        Candidate(
            product_id=product.id,
            similarity=sim,
            rating=_max_rating(listings),
            discount=_max_discount(listings),
        )
        for product, listings, sim in survivors
    ]
    scored = rank_candidates(
        cand_objs,
        w_similarity=settings.rank_w_similarity if rank_with_similarity else 0.0,
        w_discount=settings.rank_w_discount,
        w_rating=settings.rank_w_rating,
    )

    score_by_id = {s.product_id: (s.score, s.similarity) for s in scored}
    survivors_by_id = {p.id: (p, ls) for p, ls, _ in survivors}

    # Step 3: sort. `relevance` keeps the ranker's order; everything else
    # overrides with a deterministic key.
    ordered_ids: list[int]
    if sort == "price_asc":
        ordered_ids = sorted(
            survivors_by_id.keys(),
            key=lambda pid: (float(_best_listing(survivors_by_id[pid][1]).price), pid),  # type: ignore[union-attr]
        )
    elif sort == "price_desc":
        ordered_ids = sorted(
            survivors_by_id.keys(),
            key=lambda pid: (-float(_best_listing(survivors_by_id[pid][1]).price), pid),  # type: ignore[union-attr]
        )
    elif sort == "discount_desc":
        ordered_ids = sorted(
            survivors_by_id.keys(),
            key=lambda pid: (
                -float(_max_discount(survivors_by_id[pid][1]) or 0),
                pid,
            ),
        )
    elif sort == "rating_desc":
        ordered_ids = sorted(
            survivors_by_id.keys(),
            key=lambda pid: (
                -float(_max_rating(survivors_by_id[pid][1]) or 0),
                pid,
            ),
        )
    else:
        ordered_ids = [s.product_id for s in scored]

    total = len(ordered_ids)
    start = (page - 1) * page_size
    page_ids = ordered_ids[start : start + page_size]

    hits: list[SearchHit] = []
    for pid in page_ids:
        product, listings = survivors_by_id[pid]
        score, sim = score_by_id.get(pid, (0.0, 0.0))
        # Show the cheapest listings first — UI surfaces a price ladder.
        listings_sorted = sorted(listings, key=lambda l: (l.price, l.platform))
        hits.append(
            SearchHit(
                product=product,
                matching_listings=listings_sorted,
                score=score,
                similarity=sim,
            )
        )

    return SearchResult(
        query=raw_query,
        parsed_residual=parsed_residual,
        mode=mode,
        effective_mode=effective_mode,
        notes=notes,
        total=total,
        page=page,
        page_size=page_size,
        hits=hits,
    )
