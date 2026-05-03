from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    platform: str
    platform_product_id: str
    title: str
    price: Decimal
    original_price: Decimal | None = None
    discount: Decimal | None = None
    rating: Decimal | None = None
    url: str
    image_url: str | None = None
    updated_at: datetime


class SearchHitOut(ProductOut):
    score: float = 0.0
    similarity: float = 0.0


class SearchResponse(BaseModel):
    query: str
    parsed_residual: str = ""
    mode: str = "keyword"
    effective_mode: str = "keyword"
    notes: list[str] = []
    total: int
    page: int
    page_size: int
    results: list[SearchHitOut]


class ScrapedProduct(BaseModel):
    """In-memory representation produced by the scraper layer."""

    platform: str
    platform_product_id: str
    title: str
    price: Decimal
    original_price: Decimal | None = None
    discount: Decimal | None = None
    rating: Decimal | None = None
    url: str
    image_url: str | None = None


class ScrapeResult(BaseModel):
    platform: str
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    errors: int = 0
    started_at: datetime = Field(default_factory=datetime.utcnow)
    finished_at: datetime | None = None
