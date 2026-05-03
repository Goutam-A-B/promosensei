"""GET /search — cached, instrumented keyword / semantic / hybrid search.

Phase 4 wraps the Phase 3 search service with three things:

1. A pluggable cache (`memory` by default, Redis-ready) keyed on the full
   request shape — see `app.cache.build_search_cache_key`.
2. Latency measurement, exposed both in the JSON response and to
   `/metrics` for percentiles over time.
3. A `cache_hit` flag in the response body so the UI can surface it and
   so eval tooling can disambiguate cold-vs-warm latencies.
"""
import time
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.cache import build_search_cache_key, get_cache
from app.config import get_settings
from app.db import get_db
from app.observability.metrics import (
    record_cache_hit,
    record_cache_miss,
    record_search_latency,
)
from app.schemas import GroupedProductOut, ListingOut, SearchResponse
from app.search_service import search as run_search

router = APIRouter()
settings = get_settings()


def _build_response(*, result, cache_hit: bool, latency_ms: float) -> SearchResponse:
    grouped: list[GroupedProductOut] = []
    for hit in result.hits:
        product = hit.product
        listings = hit.matching_listings
        best = min(listings, key=lambda l: l.price)
        grouped.append(
            GroupedProductOut(
                id=product.id,
                canonical_title=product.canonical_title,
                brand=product.brand,
                model_number=product.model_number,
                category=product.category,
                primary_image_url=product.primary_image_url or best.image_url,
                best_price=best.price,
                best_platform=best.platform,
                platform_count=len({l.platform for l in listings}),
                listings=[ListingOut.model_validate(l) for l in listings],
                score=hit.score,
                similarity=hit.similarity,
            )
        )
    return SearchResponse(
        query=result.query,
        parsed_residual=result.parsed_residual,
        mode=result.mode,
        effective_mode=result.effective_mode,
        notes=result.notes,
        total=result.total,
        page=result.page,
        page_size=result.page_size,
        results=grouped,
        cache_hit=cache_hit,
        latency_ms=round(latency_ms, 2),
    )


@router.get("/search", response_model=SearchResponse)
def search(
    q: str = Query("", description="Free-text query. Empty returns trending deals."),
    mode: str = Query(
        settings.search_default_mode,
        pattern="^(keyword|semantic|hybrid)$",
        description="Search strategy. Default is configured via SEARCH_DEFAULT_MODE.",
    ),
    min_price: Decimal | None = Query(None, ge=0),
    max_price: Decimal | None = Query(None, ge=0),
    min_rating: Decimal | None = Query(None, ge=0, le=5),
    platform: str | None = Query(None, description="Filter to a single platform"),
    sort: str = Query(
        "relevance",
        pattern="^(relevance|price_asc|price_desc|discount_desc|rating_desc)$",
    ),
    page: int = Query(1, ge=1),
    page_size: int = Query(settings.api_default_page_size, ge=1, le=settings.api_max_page_size),
    db: Session = Depends(get_db),
) -> SearchResponse:
    started = time.perf_counter()

    cache = get_cache()
    cache_key = build_search_cache_key(
        raw_query=q,
        mode=mode,
        min_price=min_price,
        max_price=max_price,
        min_rating=min_rating,
        platform=platform,
        sort=sort,
        page=page,
        page_size=page_size,
    )

    cached = cache.get(cache_key)
    if cached is not None:
        latency_ms = (time.perf_counter() - started) * 1000
        record_cache_hit("search")
        record_search_latency(mode=mode, cached=True, latency_ms=latency_ms)
        # Cached payload is already a SearchResponse — clone with the fresh
        # cache_hit/latency rather than mutating the cached instance.
        return cached.model_copy(update={"cache_hit": True, "latency_ms": round(latency_ms, 2)})

    record_cache_miss("search")
    result = run_search(
        db,
        raw_query=q,
        mode=mode,  # type: ignore[arg-type]
        min_price=min_price,
        max_price=max_price,
        min_rating=min_rating,
        platform=platform,
        sort=sort,
        page=page,
        page_size=page_size,
    )

    latency_ms = (time.perf_counter() - started) * 1000
    response = _build_response(result=result, cache_hit=False, latency_ms=latency_ms)
    cache.set(cache_key, response, ttl_seconds=settings.cache_ttl_seconds)
    record_search_latency(mode=mode, cached=False, latency_ms=latency_ms)
    return response
