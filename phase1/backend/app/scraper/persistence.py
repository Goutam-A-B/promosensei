"""Persist scraped products into the relational store.

The matcher is intentionally simple in Phase 1: dedupe by `(platform,
platform_product_id)`. Cross-platform canonical-product matching arrives in
Phase 3 (see docs/architecture.md).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Product
from app.schemas import ScrapedProduct, ScrapeResult

logger = logging.getLogger(__name__)


def upsert_products(
    db: Session,
    products: list[ScrapedProduct],
    *,
    platform: str,
) -> ScrapeResult:
    """Insert new rows, update existing ones in-place. Returns counters."""
    result = ScrapeResult(platform=platform, started_at=datetime.now(timezone.utc))

    if not products:
        result.finished_at = datetime.now(timezone.utc)
        return result

    ids = [p.platform_product_id for p in products if p.platform == platform]
    existing_rows = db.scalars(
        select(Product).where(
            Product.platform == platform, Product.platform_product_id.in_(ids)
        )
    ).all()
    existing_by_id = {row.platform_product_id: row for row in existing_rows}

    for scraped in products:
        if scraped.platform != platform:
            result.skipped += 1
            continue
        try:
            row = existing_by_id.get(scraped.platform_product_id)
            if row is None:
                row = Product(
                    platform=scraped.platform,
                    platform_product_id=scraped.platform_product_id,
                    title=scraped.title,
                    price=scraped.price,
                    original_price=scraped.original_price,
                    discount=scraped.discount,
                    rating=scraped.rating,
                    url=scraped.url,
                    image_url=scraped.image_url,
                )
                db.add(row)
                result.inserted += 1
            else:
                row.title = scraped.title
                row.price = scraped.price
                row.original_price = scraped.original_price
                row.discount = scraped.discount
                row.rating = scraped.rating
                row.url = scraped.url
                row.image_url = scraped.image_url
                result.updated += 1
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Failed to upsert %s: %s", scraped.platform_product_id, exc)
            result.errors += 1

    db.commit()
    result.finished_at = datetime.now(timezone.utc)
    logger.info(
        "Upsert %s: inserted=%d updated=%d skipped=%d errors=%d",
        platform,
        result.inserted,
        result.updated,
        result.skipped,
        result.errors,
    )
    return result
