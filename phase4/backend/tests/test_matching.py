"""Tests for the cross-platform product matcher.

Covers the Phase 3 matcher behaviour described in canonicalize.py:

- Brand + model number is a high-confidence merge signal.
- Title fuzz handles word reordering and casing.
- Hard guards: bundle vs single, refurbished vs new, pack-size mismatch.
- Price sanity (±25%) blocks scraping bugs from collapsing real products.
"""
from __future__ import annotations

from decimal import Decimal

from app.matching import (
    extract_brand,
    extract_model_number,
    extract_pack_size,
    find_canonical_match,
    is_bundle,
    is_refurbished,
)
from app.models import Listing, Product
from app.schemas import ScrapedListing


def _scraped(
    *,
    title: str,
    price: str = "26990",
    pid: str = "FK1",
    platform: str = "flipkart",
) -> ScrapedListing:
    return ScrapedListing(
        platform=platform,
        platform_product_id=pid,
        title=title,
        price=Decimal(price),
        url=f"https://www.{platform}.com/p/{pid}",
    )


def _seed_canonical(
    db,
    *,
    title: str,
    brand: str,
    model_number: str | None = None,
    price: str = "26990",
) -> Product:
    p = Product(canonical_title=title, brand=brand, model_number=model_number)
    db.add(p)
    db.flush()
    db.add(
        Listing(
            product_id=p.id,
            platform="amazon",
            platform_product_id=f"AZ-{p.id}",
            raw_title=title,
            price=Decimal(price),
            url=f"https://www.amazon.in/dp/AZ-{p.id}",
        )
    )
    db.commit()
    return p


# --- Brand / model / pack extraction --------------------------------------


class TestExtractors:
    def test_brand_known(self):
        assert extract_brand("Sony WH-1000XM5 Wireless Headphones") == "Sony"

    def test_brand_case_insensitive(self):
        assert extract_brand("apple iPhone 15") == "Apple"

    def test_brand_word_boundary(self):
        # "Sonyish" is not Sony.
        assert extract_brand("Sonyish copycat headphones") is None

    def test_brand_none(self):
        assert extract_brand("Generic earbuds 2024") is None

    def test_model_number_extracted(self):
        assert extract_model_number("Sony WH-1000XM5 Headphones") == "WH-1000XM5"

    def test_model_number_longest_wins(self):
        # When two candidates qualify, the longest is preferred. (The regex
        # is alphanumeric-and-hyphen only — slashes inside SKUs are clipped.)
        assert extract_model_number("Phone AB12 Pro RT45T5532S8 256GB") == "RT45T5532S8"

    def test_pack_size_ml(self):
        assert extract_pack_size("Cetaphil Cleanser 250ml Sensitive") == "250ml"

    def test_pack_size_normalized(self):
        assert extract_pack_size("Detergent 1.0kg pack") == "1kg"

    def test_pack_size_pcs_alias(self):
        assert extract_pack_size("Disposable masks 50 pcs") == "50pieces"

    def test_bundle_detection(self):
        assert is_bundle("Apple iPhone 15 + AirPods Combo")
        assert not is_bundle("Apple iPhone 15")

    def test_refurbished_detection(self):
        assert is_refurbished("Apple iPhone 14 (Renewed)")
        assert not is_refurbished("Apple iPhone 14")


# --- find_canonical_match --------------------------------------------------


class TestCanonicalMatch:
    def test_brand_plus_model_matches(self, db_session):
        _seed_canonical(
            db_session,
            title="Sony WH-1000XM5 Wireless Headphones",
            brand="Sony",
            model_number="WH-1000XM5",
        )
        decision = find_canonical_match(
            db_session,
            _scraped(
                title="Sony WH-1000XM5 Active Noise Cancellation Bluetooth Headset",
                price="25990",
            ),
        )
        assert decision.matched is not None
        assert decision.matched.brand == "Sony"

    def test_different_model_does_not_match(self, db_session):
        """Edge case 3.2 — WH-1000XM4 must not collapse into WH-1000XM5."""
        _seed_canonical(
            db_session,
            title="Sony WH-1000XM5 Wireless Headphones",
            brand="Sony",
            model_number="WH-1000XM5",
            price="26990",
        )
        decision = find_canonical_match(
            db_session,
            _scraped(title="Sony WH-1000XM4 Bluetooth Headset", price="19990"),
        )
        assert decision.matched is None

    def test_bundle_blocked(self, db_session):
        """Edge case 3.3 — bundle vs single must not collapse."""
        _seed_canonical(
            db_session,
            title="Apple iPhone 15 (128 GB) Blue",
            brand="Apple",
        )
        decision = find_canonical_match(
            db_session,
            _scraped(title="Apple iPhone 15 (128 GB, Blue) + AirPods Combo Pack", price="78999"),
        )
        assert decision.matched is None
        assert "bundle" in decision.reason.lower()

    def test_refurbished_blocked(self, db_session):
        _seed_canonical(
            db_session,
            title="Apple iPhone 14 (128 GB) Black",
            brand="Apple",
        )
        decision = find_canonical_match(
            db_session,
            _scraped(title="Apple iPhone 14 (128 GB) Black (Renewed)", price="42999"),
        )
        assert decision.matched is None
        assert "refurb" in decision.reason.lower()

    def test_pack_size_mismatch_blocked(self, db_session):
        """Edge case 3.5 — 250ml and 500ml are not the same product."""
        _seed_canonical(
            db_session,
            title="Cetaphil Gentle Skin Cleanser 250ml",
            brand="Cetaphil",
        )
        decision = find_canonical_match(
            db_session,
            _scraped(title="Cetaphil Gentle Skin Cleanser 500ml", price="1199"),
        )
        assert decision.matched is None
        assert "pack" in decision.reason.lower()

    def test_price_sanity_blocks_outlier(self, db_session):
        """Scraping bug: ₹500 'iPhone' shouldn't collapse with the real one."""
        _seed_canonical(
            db_session,
            title="Apple iPhone 15 (128 GB) Blue",
            brand="Apple",
            price="66999",
        )
        decision = find_canonical_match(
            db_session,
            _scraped(title="Apple iPhone 15 128 GB Blue", price="500"),
        )
        assert decision.matched is None

    def test_no_pool_when_brand_unknown(self, db_session):
        decision = find_canonical_match(
            db_session,
            _scraped(title="Unbranded Wireless Earbuds 2024"),
        )
        assert decision.matched is None
        assert "no candidate pool" in decision.reason
