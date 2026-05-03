"""Persistence tests for the canonical-product graph.

The unit of ingest is a `ScrapedListing`. After upsert, we expect:

- A new platform/id pair adds a `Listing` row.
- A repeat platform/id pair updates the existing `Listing`.
- A scraped row tagged with the wrong platform is skipped.
- Two listings on different platforms that describe the same product collapse
  to a single `Product` with two `Listing` rows.
- Distinct products (e.g. Sony WH-1000XM4 vs WH-1000XM5) stay separate.
- Every run records a `ScraperRun` row that feeds /health/scrapers.
"""
from decimal import Decimal

from sqlalchemy import select

from app.models import Listing, Product, ScraperRun
from app.schemas import ScrapedListing
from app.scraper.persistence import upsert_listings


def _scraped(
    *,
    platform: str = "amazon",
    pid: str = "B0CHX1W1XY",
    title: str = "Sony WH-1000XM5 Wireless Noise Cancelling Headphones",
    price: str = "26990",
    original: str = "34990",
    rating: str = "4.5",
    url_prefix: str = "https://www.amazon.in/dp/",
) -> ScrapedListing:
    return ScrapedListing(
        platform=platform,
        platform_product_id=pid,
        title=title,
        price=Decimal(price),
        original_price=Decimal(original),
        discount=Decimal("23"),
        rating=Decimal(rating),
        url=f"{url_prefix}{pid}",
        image_url=None,
    )


def test_inserts_new_canonical_and_listing(db_session):
    result = upsert_listings(db_session, [_scraped()], platform="amazon")
    assert result.inserted == 1
    assert result.updated == 0
    assert db_session.scalar(select(Product).where(Product.brand == "Sony")) is not None
    listing = db_session.scalars(select(Listing)).one()
    assert listing.platform == "amazon"
    assert listing.platform_product_id == "B0CHX1W1XY"


def test_repeat_listing_updates_in_place(db_session):
    upsert_listings(db_session, [_scraped(price="26990")], platform="amazon")
    result = upsert_listings(db_session, [_scraped(price="24999")], platform="amazon")
    assert result.inserted == 0
    assert result.updated == 1
    listing = db_session.scalars(select(Listing)).one()
    assert listing.price == Decimal("24999.00")
    # Still only one canonical product.
    assert db_session.scalar(select(Listing).where(Listing.id == listing.id)) is not None
    assert len(db_session.scalars(select(Product)).all()) == 1


def test_skips_wrong_platform(db_session):
    flipkart_listing = _scraped().model_copy(update={"platform": "flipkart"})
    result = upsert_listings(db_session, [flipkart_listing], platform="amazon")
    assert result.skipped == 1
    assert result.inserted == 0
    assert db_session.scalars(select(Listing)).all() == []


def test_cross_platform_clusters_into_one_product(db_session):
    """The headline Phase 3 behaviour: same product, different platforms."""
    amazon = _scraped(
        platform="amazon",
        pid="B0CHX1W1XY",
        title="Sony WH-1000XM5 Wireless Noise Cancelling Headphones, Black",
        price="26990",
        url_prefix="https://www.amazon.in/dp/",
    )
    flipkart = _scraped(
        platform="flipkart",
        pid="ACCKT8UFPEZ6GXHZ",
        title="Sony WH1000XM5 Active Noise Cancellation Bluetooth Headset Black",
        price="25990",
        url_prefix="https://www.flipkart.com/p/",
    )

    upsert_listings(db_session, [amazon], platform="amazon")
    upsert_listings(db_session, [flipkart], platform="flipkart")

    products = db_session.scalars(select(Product)).all()
    assert len(products) == 1, "amazon + flipkart Sony WH-1000XM5 should cluster"
    listings = db_session.scalars(select(Listing)).all()
    assert {l.platform for l in listings} == {"amazon", "flipkart"}


def test_distinct_models_stay_separate(db_session):
    """Edge case 3.2 — model number differences must block a merge."""
    upsert_listings(
        db_session,
        [
            _scraped(
                pid="B0CHX1W1XY",
                title="Sony WH-1000XM5 Wireless Noise Cancelling Headphones",
            )
        ],
        platform="amazon",
    )
    upsert_listings(
        db_session,
        [
            _scraped(
                platform="flipkart",
                pid="ACCKXM4UHGVC2PKN",
                title="Sony WH-1000XM4 Bluetooth Noise Cancellation Headset",
                url_prefix="https://www.flipkart.com/p/",
            )
        ],
        platform="flipkart",
    )
    products = db_session.scalars(select(Product)).all()
    assert len(products) == 2


def test_scraper_run_recorded_on_success(db_session):
    upsert_listings(db_session, [_scraped()], platform="amazon")
    run = db_session.scalars(select(ScraperRun)).one()
    assert run.platform == "amazon"
    assert run.status == "ok"
    assert run.inserted == 1
    assert run.finished_at is not None


def test_scraper_run_recorded_on_empty_input(db_session):
    upsert_listings(db_session, [], platform="amazon")
    run = db_session.scalars(select(ScraperRun)).one()
    assert run.platform == "amazon"
    assert run.products_seen == 0
