from decimal import Decimal

from app.scraper.normalizer import (
    clean_title,
    compute_discount,
    normalize,
    parse_price,
    parse_rating,
)


class TestCleanTitle:
    def test_strips_sponsored(self):
        assert clean_title("(Sponsored) Apple iPhone 15") == "Apple iPhone 15"

    def test_strips_limited_deal(self):
        assert clean_title("[Limited Deal!] Mi Smart Band 7") == "Mi Smart Band 7"

    def test_collapses_whitespace(self):
        assert clean_title("  Sony   WH-1000XM5  ") == "Sony WH-1000XM5"

    def test_empty(self):
        assert clean_title("") == ""


class TestParsePrice:
    def test_indian_rupee_symbol(self):
        assert parse_price("₹1,999") == Decimal("1999.00")

    def test_rs_prefix(self):
        assert parse_price("Rs. 1999") == Decimal("1999.00")

    def test_inr_prefix_with_decimal(self):
        assert parse_price("INR 1,999.00") == Decimal("1999.00")

    def test_trailing_slash(self):
        assert parse_price("1999/-") == Decimal("1999.00")

    def test_returns_none_on_garbage(self):
        assert parse_price("free!") is None

    def test_returns_none_on_empty(self):
        assert parse_price("") is None
        assert parse_price(None) is None

    def test_rejects_negative(self):
        # Currency strings can't actually be negative once symbols are stripped,
        # but defensively confirm the path doesn't blow up.
        assert parse_price("-100") == Decimal("100.00")


class TestParseRating:
    def test_extracts_leading_number(self):
        assert parse_rating("4.5 out of 5 stars") == Decimal("4.50")

    def test_returns_none_when_out_of_range(self):
        assert parse_rating("99 out of 100") is None

    def test_returns_none_on_empty(self):
        assert parse_rating(None) is None
        assert parse_rating("") is None


class TestComputeDiscount:
    def test_basic(self):
        assert compute_discount(Decimal("800"), Decimal("1000")) == Decimal("20.00")

    def test_no_original(self):
        assert compute_discount(Decimal("800"), None) is None

    def test_original_le_price(self):
        assert compute_discount(Decimal("1000"), Decimal("1000")) is None
        assert compute_discount(Decimal("1000"), Decimal("900")) is None


class TestNormalize:
    def _base_args(self, **overrides):
        args = dict(
            platform="amazon",
            platform_product_id="B0CHX1W1XY",
            raw_title="Sony WH-1000XM5",
            raw_price="₹26,990",
            raw_original_price="₹34,990",
            raw_rating="4.5 out of 5 stars",
            url="https://www.amazon.in/dp/B0CHX1W1XY",
            image_url="https://example.com/img.jpg",
        )
        args.update(overrides)
        return args

    def test_happy_path(self):
        product = normalize(**self._base_args())
        assert product is not None
        assert product.title == "Sony WH-1000XM5"
        assert product.price == Decimal("26990.00")
        assert product.original_price == Decimal("34990.00")
        assert product.discount is not None
        assert product.rating == Decimal("4.50")

    def test_drops_when_price_missing(self):
        assert normalize(**self._base_args(raw_price=None)) is None

    def test_drops_when_title_blank_after_cleaning(self):
        assert normalize(**self._base_args(raw_title="(Sponsored)")) is None

    def test_drops_implausible_discount_but_keeps_listing(self):
        # original 49,999 vs current 2,499 = ~95% — should be wiped
        product = normalize(
            **self._base_args(raw_price="₹2,499", raw_original_price="₹49,999")
        )
        assert product is not None
        assert product.discount is None
        assert product.original_price is None

    def test_clears_original_when_le_price(self):
        product = normalize(
            **self._base_args(raw_price="₹1,000", raw_original_price="₹900")
        )
        assert product is not None
        assert product.original_price is None
        assert product.discount is None
