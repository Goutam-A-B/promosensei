from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.schemas import SearchHitOut, SearchResponse
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

    hits: list[SearchHitOut] = []
    for hit in result.hits:
        out = SearchHitOut.model_validate(hit.product)
        out.score = hit.score
        out.similarity = hit.similarity
        hits.append(out)

    return SearchResponse(
        query=result.query,
        parsed_residual=result.parsed_residual,
        mode=result.mode,
        effective_mode=result.effective_mode,
        notes=result.notes,
        total=result.total,
        page=result.page,
        page_size=result.page_size,
        results=hits,
    )
