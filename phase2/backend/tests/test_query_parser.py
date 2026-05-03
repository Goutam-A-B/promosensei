"""Tests for the natural-language query parser.

Covers edge case 4.5 from docs/edge-cases.md: numeric and rating constraints
embedded in free-text queries should be lifted into structured filters and
removed from the residual that gets embedded.
"""
from decimal import Decimal

from app.query_parser import parse_query


class TestPriceParsing:
    def test_under_extracts_max_price(self):
        parsed = parse_query("earbuds under 2000")
        assert parsed.max_price == Decimal("2000")
        assert parsed.min_price is None
        assert "earbuds" in parsed.residual.lower()
        assert "2000" not in parsed.residual

    def test_below_with_rupee_symbol(self):
        parsed = parse_query("moisturizer below ₹3000")
        assert parsed.max_price == Decimal("3000")
        assert "moisturizer" in parsed.residual.lower()

    def test_k_suffix_is_thousand(self):
        parsed = parse_query("phones under 10k")
        assert parsed.max_price == Decimal("10000")

    def test_above_extracts_min_price(self):
        parsed = parse_query("laptops above 50000")
        assert parsed.min_price == Decimal("50000")
        assert parsed.max_price is None

    def test_between_range(self):
        parsed = parse_query("phones between 5k and 10k")
        assert parsed.min_price == Decimal("5000")
        assert parsed.max_price == Decimal("10000")

    def test_between_swaps_when_inverted(self):
        parsed = parse_query("phones between 10k and 5k")
        assert parsed.min_price == Decimal("5000")
        assert parsed.max_price == Decimal("10000")

    def test_rs_prefix(self):
        parsed = parse_query("books under Rs. 500")
        assert parsed.max_price == Decimal("500")

    def test_inr_prefix(self):
        parsed = parse_query("monitors above INR 20000")
        assert parsed.min_price == Decimal("20000")


class TestRatingParsing:
    def test_star_phrase(self):
        parsed = parse_query("4 star earphones")
        assert parsed.min_rating == Decimal("4")
        assert "earphones" in parsed.residual.lower()

    def test_decimal_star(self):
        parsed = parse_query("4.5 star headphones")
        assert parsed.min_rating == Decimal("4.5")

    def test_rating_alt_form(self):
        parsed = parse_query("kettle rated above 4")
        assert parsed.min_rating == Decimal("4")

    def test_rating_capped_at_5(self):
        # We treat 6-star phrases as not a rating (the regex anchors to 1..5).
        parsed = parse_query("6 star hotel")
        assert parsed.min_rating is None


class TestCombinedConstraints:
    def test_rating_and_price(self):
        parsed = parse_query("4-star moisturizer under ₹3000")
        assert parsed.min_rating == Decimal("4")
        assert parsed.max_price == Decimal("3000")
        assert "moisturizer" in parsed.residual.lower()
        assert "3000" not in parsed.residual
        assert "star" not in parsed.residual.lower()

    def test_residual_is_clean(self):
        parsed = parse_query("good earbuds under 2000")
        # Residual should be the embeddable intent only.
        assert parsed.residual.strip() == "good earbuds"

    def test_empty_query(self):
        parsed = parse_query("")
        assert parsed.residual == ""
        assert parsed.min_price is None
        assert parsed.max_price is None
        assert parsed.min_rating is None

    def test_no_constraints(self):
        parsed = parse_query("wireless headphones")
        assert parsed.residual == "wireless headphones"
        assert parsed.min_price is None
        assert parsed.max_price is None

    def test_notes_are_recorded(self):
        parsed = parse_query("earbuds under 2000 rated above 4")
        assert any("max_price" in n for n in parsed.notes)
        assert any("min_rating" in n for n in parsed.notes)
