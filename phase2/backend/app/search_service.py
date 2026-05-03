"""Search orchestration: keyword, semantic, and hybrid modes.

Phase 1 only had a SQL ILIKE keyword path. Phase 2 adds:

- A `semantic` mode that embeds the query, scans the candidate vectors, and
  re-ranks via the hybrid scorer.
- A `hybrid` mode that runs both and merges. Useful for queries with strong
  keyword signal (e.g., model numbers) where pure embedding can drift.

Both vector-using modes degrade to keyword search if the index is empty (edge
case 5.1 — cold start) or if no candidates pass the filters.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.embeddings import get_embedding_provider
from app.embeddings.similarity import cosine_similarity
from app.models import Product, ProductEmbedding
from app.query_parser import ParsedQuery, parse_query
from app.ranking import Candidate, rank_candidates

logger = logging.getLogger(__name__)

SearchMode = Literal["keyword", "semantic", "hybrid"]


@dataclass
class SearchHit:
    product: Product
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
    hits: list[SearchHit]


def _apply_filters(
    stmt: Select,
    *,
    min_price: Decimal | None,
    max_price: Decimal | None,
    min_rating: Decimal | None,
    platform: str | None,
) -> Select:
    if min_price is not None:
        stmt = stmt.where(Product.price >= min_price)
    if max_price is not None:
        stmt = stmt.where(Product.price <= max_price)
    if min_rating is not None:
        stmt = stmt.where(Product.rating >= min_rating)
    if platform:
        stmt = stmt.where(Product.platform == platform)
    return stmt


def _keyword_search(
    db: Session,
    *,
    text: str,
    min_price: Decimal | None,
    max_price: Decimal | None,
    min_rating: Decimal | None,
    platform: str | None,
    sort: str,
) -> list[Product]:
    stmt = select(Product)
    tokens = [t for t in text.split() if t]
    for token in tokens:
        stmt = stmt.where(Product.title.ilike(f"%{token}%"))
    stmt = _apply_filters(
        stmt,
        min_price=min_price,
        max_price=max_price,
        min_rating=min_rating,
        platform=platform,
    )

    if sort == "price_asc":
        stmt = stmt.order_by(Product.price.asc(), Product.id.asc())
    elif sort == "price_desc":
        stmt = stmt.order_by(Product.price.desc(), Product.id.asc())
    elif sort == "discount_desc":
        stmt = stmt.order_by(Product.discount.desc().nulls_last(), Product.id.asc())
    elif sort == "rating_desc":
        stmt = stmt.order_by(Product.rating.desc().nulls_last(), Product.id.asc())
    else:
        stmt = stmt.order_by(
            Product.discount.desc().nulls_last(),
            Product.rating.desc().nulls_last(),
            Product.id.asc(),
        )

    return list(db.scalars(stmt).all())


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
    min_price: Decimal | None,
    max_price: Decimal | None,
    min_rating: Decimal | None,
    platform: str | None,
    top_k: int,
) -> list[tuple[Product, float]]:
    stmt = (
        select(Product, ProductEmbedding.vector_json)
        .join(ProductEmbedding, ProductEmbedding.product_id == Product.id)
        .where(ProductEmbedding.model_id == model_id)
    )
    stmt = _apply_filters(
        stmt,
        min_price=min_price,
        max_price=max_price,
        min_rating=min_rating,
        platform=platform,
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
            # Dimension mismatch shouldn't happen for the same model_id, but be defensive.
            continue
        scored.append((product, sim))

    scored.sort(key=lambda x: (-x[1], x[0].id))
    return scored[:top_k]


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

    # Empty query: return curated trending deals (edge case 4.1) — never embed an
    # empty string.
    if not effective_text:
        rows = _keyword_search(
            db,
            text="",
            min_price=min_price,
            max_price=max_price,
            min_rating=min_rating,
            platform=platform,
            sort=sort if sort != "relevance" else "discount_desc",
        )
        notes.append("empty query → curated trending deals")
        return _paginate(
            raw_query=raw_query,
            parsed_residual=parsed.residual,
            mode=requested_mode,
            effective_mode="keyword",
            notes=notes,
            rows=[(r, 0.0, 0.0) for r in rows],
            page=page,
            page_size=page_size,
        )

    if requested_mode == "keyword":
        rows = _keyword_search(
            db,
            text=effective_text,
            min_price=min_price,
            max_price=max_price,
            min_rating=min_rating,
            platform=platform,
            sort=sort,
        )
        return _paginate(
            raw_query=raw_query,
            parsed_residual=parsed.residual,
            mode="keyword",
            effective_mode="keyword",
            notes=notes,
            rows=[(r, 0.0, 0.0) for r in rows],
            page=page,
            page_size=page_size,
        )

    # Semantic / hybrid path
    provider = get_embedding_provider()
    if _index_size(db, provider.model_id) == 0:
        notes.append("vector index empty — falling back to keyword search")
        rows = _keyword_search(
            db,
            text=effective_text,
            min_price=min_price,
            max_price=max_price,
            min_rating=min_rating,
            platform=platform,
            sort=sort,
        )
        return _paginate(
            raw_query=raw_query,
            parsed_residual=parsed.residual,
            mode=requested_mode,
            effective_mode="keyword",
            notes=notes,
            rows=[(r, 0.0, 0.0) for r in rows],
            page=page,
            page_size=page_size,
        )

    query_vector = provider.embed([effective_text])[0]
    semantic_hits = _semantic_candidates(
        db,
        query_vector=query_vector,
        model_id=provider.model_id,
        min_price=min_price,
        max_price=max_price,
        min_rating=min_rating,
        platform=platform,
        top_k=settings.search_top_k,
    )

    if not semantic_hits:
        notes.append("no semantic candidates passed filters — falling back to keyword")
        rows = _keyword_search(
            db,
            text=effective_text,
            min_price=min_price,
            max_price=max_price,
            min_rating=min_rating,
            platform=platform,
            sort=sort,
        )
        return _paginate(
            raw_query=raw_query,
            parsed_residual=parsed.residual,
            mode=requested_mode,
            effective_mode="keyword",
            notes=notes,
            rows=[(r, 0.0, 0.0) for r in rows],
            page=page,
            page_size=page_size,
        )

    # Hybrid: union the semantic candidates with keyword matches so we don't
    # miss exact-phrase hits.
    candidate_ids: set[int] = {p.id for p, _ in semantic_hits}
    candidates_by_id: dict[int, tuple[Product, float]] = {p.id: (p, sim) for p, sim in semantic_hits}

    if requested_mode == "hybrid":
        keyword_rows = _keyword_search(
            db,
            text=effective_text,
            min_price=min_price,
            max_price=max_price,
            min_rating=min_rating,
            platform=platform,
            sort="relevance",
        )
        for row in keyword_rows:
            if row.id not in candidate_ids:
                # Score it 0.0 — re-ranker still considers discount + rating signals.
                candidates_by_id[row.id] = (row, 0.0)
                candidate_ids.add(row.id)

    cand_objs = [
        Candidate(
            product_id=p.id,
            similarity=sim,
            rating=p.rating,
            discount=p.discount,
        )
        for p, sim in candidates_by_id.values()
    ]
    scored = rank_candidates(
        cand_objs,
        w_similarity=settings.rank_w_similarity,
        w_discount=settings.rank_w_discount,
        w_rating=settings.rank_w_rating,
    )

    # Honor explicit sort overrides — relevance is the default for semantic mode.
    if sort == "price_asc":
        scored.sort(
            key=lambda s: (
                float(candidates_by_id[s.product_id][0].price),
                s.product_id,
            )
        )
    elif sort == "price_desc":
        scored.sort(
            key=lambda s: (
                -float(candidates_by_id[s.product_id][0].price),
                s.product_id,
            )
        )
    elif sort == "discount_desc":
        scored.sort(
            key=lambda s: (
                -float(candidates_by_id[s.product_id][0].discount or 0),
                s.product_id,
            )
        )
    elif sort == "rating_desc":
        scored.sort(
            key=lambda s: (
                -float(candidates_by_id[s.product_id][0].rating or 0),
                s.product_id,
            )
        )

    rows = [
        (candidates_by_id[s.product_id][0], s.score, s.similarity) for s in scored
    ]
    return _paginate(
        raw_query=raw_query,
        parsed_residual=parsed.residual,
        mode=requested_mode,
        effective_mode=requested_mode,
        notes=notes,
        rows=rows,
        page=page,
        page_size=page_size,
    )


def _paginate(
    *,
    raw_query: str,
    parsed_residual: str,
    mode: SearchMode,
    effective_mode: SearchMode,
    notes: list[str],
    rows: list[tuple[Product, float, float]],
    page: int,
    page_size: int,
) -> SearchResult:
    total = len(rows)
    start = (page - 1) * page_size
    page_rows = rows[start : start + page_size]
    hits = [SearchHit(product=p, score=score, similarity=sim) for p, score, sim in page_rows]
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
