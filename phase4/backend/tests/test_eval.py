"""Eval harness: metrics math + end-to-end on the seeded fixture catalog."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from app.embeddings import reindex_products, reset_provider_cache
from app.eval import EvalCase, dcg, evaluate, load_cases, ndcg, precision_at_k
from app.models import Listing, Product


# ---- Pure metrics ----------------------------------------------------------


def test_dcg_textbook_value():
    # rel = [3, 2, 3, 0, 1, 2] → dcg = 3 + 2/log2(3) + 3/log2(4) + 0 + 1/log2(6) + 2/log2(7)
    assert dcg([3, 2, 3, 0, 1, 2]) == pytest.approx(6.861, abs=1e-3)


def test_ndcg_perfect_ranking_is_1():
    assert ndcg([1, 1, 1, 0, 0]) == pytest.approx(1.0)


def test_ndcg_zero_when_no_relevant_docs():
    assert ndcg([0, 0, 0]) == 0.0


def test_ndcg_inverted_ranking_below_perfect():
    perfect = ndcg([1, 1, 0, 0])
    inverted = ndcg([0, 0, 1, 1])
    assert inverted < perfect


def test_precision_at_k_basic():
    assert precision_at_k([1, 0, 1, 0], k=3) == pytest.approx(2 / 3)
    assert precision_at_k([0, 0, 0], k=3) == 0.0
    assert precision_at_k([1, 1], k=5) == pytest.approx(1.0)
    assert precision_at_k([], k=3) == 0.0


# ---- YAML loader ----------------------------------------------------------


def test_load_cases_default_file_parses():
    cases = load_cases()
    assert cases, "default queries.yaml should not be empty"
    for case in cases:
        assert case.query
        assert case.relevant_terms
        assert case.mode in {"keyword", "semantic", "hybrid"}


def test_load_cases_skips_malformed_entries(tmp_path: Path):
    bad_file = tmp_path / "q.yaml"
    bad_file.write_text(
        """
- query: "earbuds"
  relevant: ["buds"]
- not_a_dict
- query: "missing_relevant"
""",
        encoding="utf-8",
    )
    cases = load_cases(bad_file)
    assert len(cases) == 1
    assert cases[0].query == "earbuds"


# ---- End-to-end eval against seeded catalog -------------------------------


def _seed_catalog(db) -> None:
    """Seed enough cross-platform products to exercise every eval query."""
    rows: list[tuple[str, str | None, list[dict]]] = [
        (
            "boAt Airdopes 141 Bluetooth Earbuds",
            "boAt",
            [dict(platform="amazon", pid="B1", price=1299, rating=4.1)],
        ),
        (
            "Samsung Galaxy Buds 2 Pro Bluetooth Earbuds with Mic",
            "Samsung",
            [dict(platform="amazon", pid="S1", price=12999, rating=4.4)],
        ),
        (
            "Sony WH-1000XM5 Wireless Noise Cancellation Headset",
            "Sony",
            [dict(platform="amazon", pid="SO1", price=26990, rating=4.5)],
        ),
        (
            "Sony WH-1000XM4 Bluetooth Noise Cancellation Headset",
            "Sony",
            [dict(platform="flipkart", pid="SO2", price=21990, rating=4.4)],
        ),
        (
            "Apple iPhone 15 (128 GB) Blue",
            "Apple",
            [dict(platform="amazon", pid="AP1", price=66999, rating=4.6)],
        ),
        (
            "Apple iPhone 15 (128 GB) + AirPods Combo",
            "Apple",
            [dict(platform="flipkart", pid="AP2", price=74999, rating=4.5)],
        ),
        (
            "Mi Smart Band 7 Fitness Tracker",
            "Mi",
            [dict(platform="flipkart", pid="MI1", price=2799, rating=4.3)],
        ),
        (
            "Logitech MX Master 3S Wireless Mouse",
            "Logitech",
            [dict(platform="amazon", pid="LO1", price=8995, rating=4.7)],
        ),
        (
            "Lenovo IdeaPad Slim 3 Intel Core i5 12th Gen Laptop",
            "Lenovo",
            [dict(platform="flipkart", pid="LE1", price=54990, rating=4.2)],
        ),
        (
            "Cetaphil Gentle Skin Cleanser 250ml",
            "Cetaphil",
            [dict(platform="amazon", pid="CE1", price=499, rating=4.6)],
        ),
        (
            "Lakme Absolute 3D Smooth Matte Foundation 25g",
            "Lakme",
            [dict(platform="amazon", pid="LA1", price=1199, rating=4.2)],
        ),
        (
            "Mamaearth Vitamin C Face Wash with Vitamin C and Turmeric",
            "Mamaearth",
            [dict(platform="nykaa", pid="MA1", price=249, rating=4.4)],
        ),
        (
            "Plum Green Tea Toner with Witch Hazel",
            "Plum",
            [dict(platform="nykaa", pid="PL1", price=390, rating=4.5)],
        ),
    ]

    for canonical_title, brand, listings in rows:
        product = Product(canonical_title=canonical_title, brand=brand)
        db.add(product)
        db.flush()
        for spec in listings:
            db.add(
                Listing(
                    product_id=product.id,
                    platform=spec["platform"],
                    platform_product_id=spec["pid"],
                    raw_title=canonical_title,
                    price=Decimal(str(spec["price"])),
                    rating=Decimal(str(spec["rating"])),
                    url=f"https://{spec['platform']}.example/{spec['pid']}",
                    last_seen_at=datetime.now(timezone.utc),
                )
            )
    db.commit()


@pytest.fixture()
def seeded_db(db_session):
    reset_provider_cache()
    _seed_catalog(db_session)
    reindex_products(db_session)
    yield db_session
    reset_provider_cache()


def test_evaluate_returns_summary_metrics(seeded_db):
    cases = [
        EvalCase(query="earbuds", relevant_terms=["buds", "earbuds", "airdopes"]),
        EvalCase(query="lakme foundation", relevant_terms=["lakme", "foundation"]),
    ]
    report = evaluate(seeded_db, cases=cases, page_size=5)
    assert len(report.cases) == 2
    assert report.coverage > 0
    assert report.hit_rate > 0
    assert 0.0 <= report.mean_ndcg_at_5 <= 1.0


def test_evaluate_full_default_set_meets_baseline(seeded_db):
    """Smoke test — make sure the bundled queries.yaml clears the floor on
    the seeded catalog. This is *not* the regression gate; that lives in
    `test_eval_regression.py` which uses the configured threshold."""
    report = evaluate(seeded_db, page_size=10)
    summary = report.as_dict()["summary"]
    assert summary["coverage"] >= 0.8
    assert summary["hit_rate"] >= 0.6
