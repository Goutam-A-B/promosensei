from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Index, Numeric, String, UniqueConstraint, func
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
