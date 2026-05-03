"""GET /search — keyword / semantic / hybrid over the canonical-product graph.

Phase 3 returns *grouped* products: one card per canonical Product with its
per-platform offers attached. The Phase 1/2 flat shape is gone — see
`GroupedProductOut` in `app.schemas`.
"""
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.schemas import GroupedProductOut, ListingOut, SearchResponse
from app.search_service import search as run_search

router = APIRouter()
settings = get_settings()


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
    )
