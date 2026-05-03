"""Persist scraped listings into the canonical-product graph.

Pipeline per scraped batch:

1. Validate platform and skip rows that don't match.
2. For each row:
   a. Try to find an existing `Listing` by (platform, platform_product_id).
      If it's there, just update price/rating/freshness. The `product_id`
      stays put — the listing was already matched on a previous run.
   b. Otherwise, run the matcher against existing canonical products.
      - Match → upsert a new `Listing` pointing at the matched product.
      - No match → create a new canonical `Product` *and* its first listing.
3. Record a `ScraperRun` row regardless of outcome (feeds /health/scrapers).

Steps 2b and 3 are what make Phase 3 "cross-platform aggregation": the
same product on three platforms ends up with one `products` row and three
`listings` rows.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.embeddings import get_embedding_provider
from app.matching import (
    canonical_title_for,
    extract_brand,
    extract_model_number,
    find_canonical_match,
)
from app.models import Listing, Product, ScraperRun
from app.schemas import ScrapedListing, ScrapeResult

logger = logging.getLogger(__name__)


def upsert_listings(
    db: Session,
    listings: list[ScrapedListing],
    *,
    platform: str,
) -> ScrapeResult:
    """Insert/update listings for a single platform; cluster across platforms.

    The `platform` argument is enforced — listings whose `platform` field
    doesn't match it are counted as `skipped` and ignored. This is a
    defensive guard against scrapers that accidentally tag rows with the
    wrong platform.
    """
    started = datetime.now(timezone.utc)
    result = ScrapeResult(platform=platform, started_at=started)
    run = ScraperRun(platform=platform, started_at=started, status="ok")
    db.add(run)

    if not listings:
        run.finished_at = datetime.now(timezone.utc)
        db.commit()
        result.finished_at = run.finished_at
        return result

    run.products_seen = sum(1 for r in listings if r.platform == platform)

    # Pre-load existing listings for this platform so we don't query per-row.
    incoming_ids = [l.platform_product_id for l in listings if l.platform == platform]
    existing_listings = {
        row.platform_product_id: row
        for row in db.scalars(
            select(Listing).where(
                Listing.platform == platform, Listing.platform_product_id.in_(incoming_ids)
            )
        ).all()
    }

    provider = None
    try:
        provider = get_embedding_provider()
    except Exception:  # noqa: BLE001 — provider is best-effort during ingest
        logger.warning("Embedding provider unavailable — falling back to fuzz-only matching")

    for scraped in listings:
        if scraped.platform != platform:
            result.skipped += 1
            continue
        try:
            existing = existing_listings.get(scraped.platform_product_id)
            if existing is not None:
                _update_listing(existing, scraped)
                result.updated += 1
                continue

            # New listing on this platform — try to match against canonical pool.
            listing_vector: list[float] | None = None
            if provider is not None:
                try:
                    listing_vector = provider.embed([scraped.title])[0]
                except Exception:  # noqa: BLE001
                    listing_vector = None

            decision = find_canonical_match(
                db,
                scraped,
                embedding_provider=provider,
                listing_vector=listing_vector,
            )
            if decision.matched is not None:
                product = decision.matched
                logger.info(
                    "Matched %s/%s -> product#%d (%s)",
                    scraped.platform, scraped.platform_product_id, product.id, decision.reason,
                )
            else:
                product = _create_canonical(db, scraped)
                logger.info(
                    "New canonical product#%d for %s/%s (matcher: %s)",
                    product.id, scraped.platform, scraped.platform_product_id, decision.reason,
                )

            db.add(_build_listing(product, scraped))
            result.inserted += 1
        except Exception as exc:  # noqa: BLE001 - keep ingesting on per-row failure
            logger.exception("Failed to ingest %s: %s", scraped.platform_product_id, exc)
            result.errors += 1

    if result.errors > 0 and result.inserted + result.updated == 0:
        run.status = "failed"
    elif result.errors > 0:
        run.status = "partial"
    run.inserted = result.inserted
    run.updated = result.updated
    run.skipped = result.skipped
    run.errors = result.errors
    run.finished_at = datetime.now(timezone.utc)

    db.commit()
    result.finished_at = run.finished_at
    logger.info(
        "Upsert %s: inserted=%d updated=%d skipped=%d errors=%d (status=%s)",
        platform,
        result.inserted,
        result.updated,
        result.skipped,
        result.errors,
        run.status,
    )
    return result


# Phase 1/2 callers used `upsert_products` — keep the alias so old scripts work.
upsert_products = upsert_listings


def _update_listing(row: Listing, scraped: ScrapedListing) -> None:
    row.raw_title = scraped.title
    row.price = scraped.price
    row.original_price = scraped.original_price
    row.discount = scraped.discount
    row.rating = scraped.rating
    row.url = scraped.url
    row.image_url = scraped.image_url
    row.last_seen_at = datetime.now(timezone.utc)


def _build_listing(product: Product, scraped: ScrapedListing) -> Listing:
    return Listing(
        product=product,
        platform=scraped.platform,
        platform_product_id=scraped.platform_product_id,
        raw_title=scraped.title,
        price=scraped.price,
        original_price=scraped.original_price,
        discount=scraped.discount,
        rating=scraped.rating,
        url=scraped.url,
        image_url=scraped.image_url,
        last_seen_at=datetime.now(timezone.utc),
    )


def _create_canonical(db: Session, scraped: ScrapedListing) -> Product:
    product = Product(
        canonical_title=canonical_title_for(scraped),
        brand=extract_brand(scraped.title),
        model_number=extract_model_number(scraped.title),
        primary_image_url=scraped.image_url,
    )
    db.add(product)
    # Flush so the matcher's next call sees the just-created product.
    db.flush()
    return product
