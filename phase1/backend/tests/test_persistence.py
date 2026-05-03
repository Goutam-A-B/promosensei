from decimal import Decimal

from sqlalchemy import select

from app.models import Product
from app.schemas import ScrapedProduct
from app.scraper.persistence import upsert_products


def _scraped(asin: str = "B0TEST00001", price: str = "1000") -> ScrapedProduct:
    return ScrapedProduct(
        platform="amazon",
        platform_product_id=asin,
        title=f"Test product {asin}",
        price=Decimal(price),
        original_price=Decimal("2000"),
        discount=Decimal("50"),
        rating=Decimal("4.2"),
        url=f"https://www.amazon.in/dp/{asin}",
        image_url=None,
    )


def test_inserts_new_rows(db_session):
    result = upsert_products(db_session, [_scraped()], platform="amazon")
    assert result.inserted == 1
    assert result.updated == 0
    rows = db_session.scalars(select(Product)).all()
    assert len(rows) == 1
    assert rows[0].platform_product_id == "B0TEST00001"


def test_upsert_updates_existing(db_session):
    upsert_products(db_session, [_scraped(price="1000")], platform="amazon")
    result = upsert_products(db_session, [_scraped(price="900")], platform="amazon")
    assert result.inserted == 0
    assert result.updated == 1
    row = db_session.scalars(select(Product)).one()
    assert row.price == Decimal("900.00")


def test_skips_wrong_platform(db_session):
    flipkart_product = _scraped().model_copy(update={"platform": "flipkart"})
    result = upsert_products(db_session, [flipkart_product], platform="amazon")
    assert result.skipped == 1
    assert result.inserted == 0
