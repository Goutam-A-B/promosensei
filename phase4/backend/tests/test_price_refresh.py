"""Incremental price-only refresher (`refresh_prices`)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.models import Listing, Product
from app.scraper import refresh_prices
from app.schemas import ScrapedListing


def _seed_listing(db, *, platform: str, pid: str, price: str = "1000", rating: str = "4.0"):
    product = Product(canonical_title="boAt Airdopes 141", brand="boAt")
    db.add(product)
    db.flush()
    listing = Listing(
        product_id=product.id,
        platform=platform,
        platform_product_id=pid,
        raw_title="boAt Airdopes 141 TWS",
        price=Decimal(price),
        original_price=Decimal("2990"),
        discount=Decimal("66.55"),
        rating=Decimal(rating),
        url="https://amazon.in/x",
        last_seen_at=datetime.now(timezone.utc) - timedelta(hours=10),
    )
    db.add(listing)
    db.commit()
    return product, listing


def _scraped(*, platform: str, pid: str, price: str, rating: str | None = "4.2") -> ScrapedListing:
    return ScrapedListing(
        platform=platform,
        platform_product_id=pid,
        title="boAt Airdopes 141 TWS",
        price=Decimal(price),
        original_price=Decimal("2990"),
        discount=Decimal("70.00"),
        rating=Decimal(rating) if rating else None,
        url="https://amazon.in/x",
    )


def test_refresh_updates_price_and_rating(db_session):
    db = db_session
    _, listing = _seed_listing(db, platform="amazon", pid="A1", price="1500")
    listing_id = listing.id

    result = refresh_prices(
        db,
        [_scraped(platform="amazon", pid="A1", price="999", rating="4.4")],
        platform="amazon",
    )
    assert result.updated == 1
    assert result.errors == 0

    refreshed = db.get(Listing, listing_id)
    assert refreshed.price == Decimal("999.00")
    assert refreshed.rating == Decimal("4.40")


def test_refresh_skips_unknown_platform_product_id(db_session):
    db = db_session
    _seed_listing(db, platform="amazon", pid="A1")

    result = refresh_prices(
        db,
        [_scraped(platform="amazon", pid="UNKNOWN", price="500")],
        platform="amazon",
    )
    # Unknown listing is skipped — refresher must NOT create new products.
    assert result.updated == 0
    assert result.skipped == 1
    products = db.query(Product).count()
    assert products == 1


def test_refresh_skips_listings_fresher_than_max_age(db_session):
    db = db_session
    product = Product(canonical_title="Sony WH-1000XM5", brand="Sony")
    db.add(product)
    db.flush()
    fresh = Listing(
        product_id=product.id,
        platform="amazon",
        platform_product_id="A2",
        raw_title="Sony WH-1000XM5",
        price=Decimal("26990"),
        url="https://x",
        last_seen_at=datetime.now(timezone.utc),  # very fresh
    )
    db.add(fresh)
    db.commit()

    result = refresh_prices(
        db,
        [_scraped(platform="amazon", pid="A2", price="20000")],
        platform="amazon",
        max_age_hours=1,
    )
    assert result.updated == 0
    assert result.skipped == 1
    # Price is unchanged.
    assert db.get(Listing, fresh.id).price == Decimal("26990.00")


def test_refresh_skips_rows_for_other_platforms(db_session):
    db = db_session
    _seed_listing(db, platform="amazon", pid="A1")

    # Pass a flipkart row when we're refreshing amazon — should be skipped.
    result = refresh_prices(
        db,
        [_scraped(platform="flipkart", pid="A1", price="999")],
        platform="amazon",
    )
    assert result.updated == 0
    assert result.skipped == 1


def test_refresh_records_scraper_run_status(db_session):
    db = db_session
    _seed_listing(db, platform="amazon", pid="A1")
    refresh_prices(
        db,
        [_scraped(platform="amazon", pid="A1", price="500")],
        platform="amazon",
    )
    from app.models import ScraperRun

    run = db.query(ScraperRun).order_by(ScraperRun.id.desc()).first()
    assert run is not None
    assert run.platform == "amazon"
    assert run.status == "ok"
    assert run.updated == 1
