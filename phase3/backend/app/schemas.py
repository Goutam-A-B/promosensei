from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


# --- Scraper output ----------------------------------------------------------


class ScrapedListing(BaseModel):
    """In-memory representation produced by a platform scraper.

    A listing is platform-specific: the same canonical product on Amazon and
    Flipkart yields two `ScrapedListing` rows. The matcher decides whether
    they collapse into one canonical product downstream.
    """

    platform: str
    platform_product_id: str
    title: str
    price: Decimal
    original_price: Decimal | None = None
    discount: Decimal | None = None
    rating: Decimal | None = None
    url: str
    image_url: str | None = None


# Backwards-compatibility alias — Phase 1/2 code calls this ScrapedProduct.
# Removable once all callers are migrated.
ScrapedProduct = ScrapedListing


class ScrapeResult(BaseModel):
    platform: str
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    errors: int = 0
    started_at: datetime = Field(default_factory=datetime.utcnow)
    finished_at: datetime | None = None


# --- Search output -----------------------------------------------------------


class ListingOut(BaseModel):
    """One platform's offer surfaced inside a grouped product result."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    platform: str
    platform_product_id: str
    price: Decimal
    original_price: Decimal | None = None
    discount: Decimal | None = None
    rating: Decimal | None = None
    url: str
    image_url: str | None = None
    last_seen_at: datetime


class GroupedProductOut(BaseModel):
    """A canonical product with its per-platform offers, sorted cheapest first."""

    # `model_number` collides with pydantic's "model_" protected prefix —
    # disabling the namespace lets the field through without a warning.
    model_config = ConfigDict(protected_namespaces=())

    id: int
    canonical_title: str
    brand: str | None = None
    model_number: str | None = None
    category: str | None = None
    primary_image_url: str | None = None

    best_price: Decimal
    best_platform: str
    platform_count: int
    listings: list[ListingOut]

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
    results: list[GroupedProductOut]


# --- Health output -----------------------------------------------------------


class ScraperHealth(BaseModel):
    platform: str
    last_started_at: datetime | None = None
    last_finished_at: datetime | None = None
    last_status: str | None = None
    success_rate_30d: float = 0.0  # 0..1
    runs_30d: int = 0
    listings_count: int = 0
    last_error: str | None = None


class ScrapersHealthResponse(BaseModel):
    scrapers: list[ScraperHealth]
