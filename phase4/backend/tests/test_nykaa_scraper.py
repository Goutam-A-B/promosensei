"""Smoke + correctness checks for the Nykaa fixture scraper."""
from decimal import Decimal
from pathlib import Path

import pytest

from app.scraper.nykaa import NykaaScraper, _parse_html


@pytest.fixture()
def nykaa_fixtures_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "fixtures" / "nykaa"


def test_parses_fixture_listings(nykaa_fixtures_dir):
    html = (nykaa_fixtures_dir / "deals_page1.html").read_text(encoding="utf-8")
    listings = _parse_html(html)

    skus = {l.platform_product_id for l in listings}
    # Cross-platform overlap candidates with Amazon (Cetaphil 250ml, Lakme).
    assert "123456" in skus
    assert "234567" in skus
    # Pre-launch product without a price must be dropped by the normalizer.
    assert "567890" not in skus

    cetaphil = next(l for l in listings if l.platform_product_id == "123456")
    assert "Cetaphil" in cetaphil.title
    assert cetaphil.price == Decimal("685.00")
    assert cetaphil.platform == "nykaa"
    assert cetaphil.url.startswith("https://www.nykaa.com/")


def test_scraper_uses_fixtures_dir(nykaa_fixtures_dir):
    scraper = NykaaScraper(use_fixtures=True, fixtures_dir=nykaa_fixtures_dir)
    listings = scraper.scrape()
    assert len(listings) >= 4
