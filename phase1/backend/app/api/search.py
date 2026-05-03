from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import Product
from app.schemas import ProductOut, SearchResponse

router = APIRouter()
settings = get_settings()


@router.get("/search", response_model=SearchResponse)
def search(
    q: str = Query("", description="Free-text query. Empty returns trending deals."),
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
    stmt = select(Product)
    count_stmt = select(func.count(Product.id))

    query = (q or "").strip()
    if query:
        tokens = [t for t in query.split() if t]
        for token in tokens:
            like = f"%{token}%"
            stmt = stmt.where(Product.title.ilike(like))
            count_stmt = count_stmt.where(Product.title.ilike(like))

    if min_price is not None:
        stmt = stmt.where(Product.price >= min_price)
        count_stmt = count_stmt.where(Product.price >= min_price)
    if max_price is not None:
        stmt = stmt.where(Product.price <= max_price)
        count_stmt = count_stmt.where(Product.price <= max_price)
    if min_rating is not None:
        stmt = stmt.where(Product.rating >= min_rating)
        count_stmt = count_stmt.where(Product.rating >= min_rating)
    if platform:
        stmt = stmt.where(Product.platform == platform)
        count_stmt = count_stmt.where(Product.platform == platform)

    if sort == "price_asc":
        stmt = stmt.order_by(Product.price.asc())
    elif sort == "price_desc":
        stmt = stmt.order_by(Product.price.desc())
    elif sort == "discount_desc":
        stmt = stmt.order_by(Product.discount.desc().nulls_last())
    elif sort == "rating_desc":
        stmt = stmt.order_by(Product.rating.desc().nulls_last())
    else:
        stmt = stmt.order_by(
            Product.discount.desc().nulls_last(),
            Product.rating.desc().nulls_last(),
        )

    total = db.scalar(count_stmt) or 0
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    rows = db.scalars(stmt).all()

    return SearchResponse(
        query=query,
        total=total,
        page=page,
        page_size=page_size,
        results=[ProductOut.model_validate(r) for r in rows],
    )
