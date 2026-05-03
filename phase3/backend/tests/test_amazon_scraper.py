from decimal import Decimal

from app.scraper.amazon import AmazonScraper, _parse_html


def test_parses_fixture_products(fixtures_dir):
    html = (fixtures_dir / "deals_page1.html").read_text(encoding="utf-8")
    products = _parse_html(html)

    asins = {p.platform_product_id for p in products}
    # 10 cards in fixture, 1 (no price) is rejected by normalizer.
    assert "B0CHX1W1XY" in asins
    assert "B09G9HD6PD" in asins
    assert "B0CCC00003" not in asins, "Card without price must be dropped"

    sony = next(p for p in products if p.platform_product_id == "B0CHX1W1XY")
    assert "Sony" in sony.title
    assert sony.price == Decimal("26990.00")
    assert sony.url.startswith("https://www.amazon.in/")
    assert sony.rating == Decimal("4.50")


def test_sponsored_marker_stripped_from_title(fixtures_dir):
    html = (fixtures_dir / "deals_page1.html").read_text(encoding="utf-8")
    products = _parse_html(html)
    boat = next(p for p in products if p.platform_product_id == "B09G9HD6PD")
    assert "Sponsored" not in boat.title


def test_implausible_discount_dropped(fixtures_dir):
    html = (fixtures_dir / "deals_page1.html").read_text(encoding="utf-8")
    products = _parse_html(html)
    laptop = next(p for p in products if p.platform_product_id == "B0DDD00004")
    assert laptop.discount is None
    assert laptop.original_price is None


def test_scraper_uses_fixtures_dir(fixtures_dir):
    scraper = AmazonScraper(use_fixtures=True, fixtures_dir=fixtures_dir)
    products = scraper.scrape()
    assert len(products) >= 8
