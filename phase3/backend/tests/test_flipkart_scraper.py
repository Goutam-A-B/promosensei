"""Smoke + correctness checks for the Flipkart fixture scraper.

We don't hit Flipkart over the network — the parser is exercised against a
checked-in fixture HTML so the test stays deterministic and offline.
"""
from decimal import Decimal
from pathlib import Path

import pytest

from app.scraper.flipkart import FlipkartScraper, _parse_html


@pytest.fixture()
def flipkart_fixtures_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "fixtures" / "flipkart"


def test_parses_fixture_listings(flipkart_fixtures_dir):
    html = (flipkart_fixtures_dir / "deals_page1.html").read_text(encoding="utf-8")
    listings = _parse_html(html)

    fsns = {l.platform_product_id for l in listings}
    # Cross-platform overlap with Amazon: Sony WH-1000XM5, iPhone 15, boAt 141, Mi Band 7.
    # Flipkart's data-fsn is lowercase — keep it that way so the (platform,
    # platform_product_id) uniqueness contract is stable across runs.
    assert "acckt8ufpez6gxhz" in fsns
    assert "moblh9j4hzvyc6ma" in fsns
    assert "acccyxbufdgvn4tz" in fsns

    sony = next(l for l in listings if l.platform_product_id == "acckt8ufpez6gxhz")
    assert "Sony" in sony.title
    assert sony.price == Decimal("25990.00")
    assert sony.url.startswith("https://www.flipkart.com/")
    assert sony.platform == "flipkart"


def test_scraper_uses_fixtures_dir(flipkart_fixtures_dir):
    scraper = FlipkartScraper(use_fixtures=True, fixtures_dir=flipkart_fixtures_dir)
    listings = scraper.scrape()
    assert len(listings) >= 5


def test_dedupes_within_a_run(flipkart_fixtures_dir):
    scraper = FlipkartScraper(use_fixtures=True, fixtures_dir=flipkart_fixtures_dir)
    listings = scraper.scrape()
    fsns = [l.platform_product_id for l in listings]
    assert len(fsns) == len(set(fsns))
