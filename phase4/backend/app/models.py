"""Phase 3 schema: canonical products + per-platform listings.

Phase 1 + 2 used a flat `products` table where one row meant "this offer on
Amazon". Phase 3 separates the *thing* (canonical product) from *where it's
sold* (per-platform listing). A Sony WH-1000XM5 gets one `Product` row plus
one `Listing` row per platform that carries it. Embeddings hang off the
canonical product so we don't redundantly embed three near-identical titles.

`scraper_runs` is the per-invocation log that feeds /health/scrapers — the
per-platform success-rate metric called out in the Phase 3 architecture.
"""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Product(Base):
    """Canonical product — one row per real-world item, regardless of platform."""

    __tablename__ = "products"
    __table_args__ = (
        Index("ix_products_canonical_title", "canonical_title"),
        Index("ix_products_brand", "brand"),
        Index("ix_products_model_number", "model_number"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    canonical_title: Mapped[str] = mapped_column(String(1024), nullable=False)
    brand: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Model number for electronics ("WH-1000XM5"), pack size for FMCG ("250ml"),
    # etc. — anything that disambiguates within a brand.
    model_number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    primary_image_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    # Hash of the embed-text. The indexer re-embeds when this changes
    # (edge case 5.3 — stale embeddings after a canonical-title rewrite).
    title_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    listings: Mapped[list["Listing"]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Listing(Base):
    """One platform's offer for a canonical product."""

    __tablename__ = "listings"
    __table_args__ = (
        UniqueConstraint("platform", "platform_product_id", name="uq_platform_product"),
        Index("ix_listings_product", "product_id"),
        Index("ix_listings_platform", "platform"),
        Index("ix_listings_price", "price"),
        Index("ix_listings_last_seen", "last_seen_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )

    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    platform_product_id: Mapped[str] = mapped_column(String(128), nullable=False)

    # The raw title as scraped — kept for debugging and for the matcher to
    # re-evaluate without re-scraping (edge case 2.8 — title noise).
    raw_title: Mapped[str] = mapped_column(String(1024), nullable=False)

    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    original_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    discount: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)

    rating: Mapped[Decimal | None] = mapped_column(Numeric(3, 2), nullable=True)

    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    image_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    # Freshness signal for Phase 4's price refresher and for /health/scrapers.
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    product: Mapped[Product] = relationship(back_populates="listings")


class ProductEmbedding(Base):
    """One vector per (canonical product, model) pair.

    Storing `model_id` keeps Phase 2/3 future-proof: when we upgrade the
    embedding model, we keep both vector sets during the cutover and only
    delete the old ones once the index is rebuilt (edge case 5.2).
    """

    __tablename__ = "product_embeddings"
    __table_args__ = (
        UniqueConstraint("product_id", "model_id", name="uq_product_embedding_model"),
        Index("ix_product_embeddings_model", "model_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    model_id: Mapped[str] = mapped_column(String(128), nullable=False)
    dim: Mapped[int] = mapped_column(Integer, nullable=False)
    # Vector serialized as JSON array of floats. Phase 4 swaps for pgvector.
    vector_json: Mapped[str] = mapped_column(Text, nullable=False)
    title_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class ScraperRun(Base):
    """Per-invocation log feeding /health/scrapers.

    One row per scrape attempt — successful or not. Read by the health
    endpoint to compute success-rate-over-N-days and last-success time per
    platform (architecture.md Phase 3 exit criteria).
    """

    __tablename__ = "scraper_runs"
    __table_args__ = (
        Index("ix_scraper_runs_platform", "platform"),
        Index("ix_scraper_runs_started_at", "started_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # ok | partial | failed
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ok")

    products_seen: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    inserted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    errors: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
