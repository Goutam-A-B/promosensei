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
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("platform", "platform_product_id", name="uq_platform_product"),
        Index("ix_products_title", "title"),
        Index("ix_products_platform", "platform"),
        Index("ix_products_price", "price"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    platform_product_id: Mapped[str] = mapped_column(String(128), nullable=False)

    title: Mapped[str] = mapped_column(String(1024), nullable=False)
    # Hash of the embed-text, used by the indexer to detect stale vectors
    # (edge case 5.3 — re-embed when title changes).
    title_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    original_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    discount: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)

    rating: Mapped[Decimal | None] = mapped_column(Numeric(3, 2), nullable=True)

    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    image_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class ProductEmbedding(Base):
    """One vector per (product, model) pair.

    Storing `model_id` keeps Phase 2 future-proof: when we upgrade the
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
