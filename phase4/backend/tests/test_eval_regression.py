"""CI ranking-quality gate.

Runs the bundled query set against the seeded catalog and asserts the
two headline metrics stay above the floor in `app.config`. If a future
ranker change drops NDCG@5 / Precision@3 below those numbers, this test
fails the build before merge.

The thresholds are deliberately conservative — tighten them once the
real catalog is in play and we have stable baselines.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.config import get_settings
from app.embeddings import reindex_products, reset_provider_cache
from app.eval import evaluate
from app.models import Listing, Product


def _seed_catalog(db) -> None:
    rows = [
        ("boAt Airdopes 141 Bluetooth Earbuds", "boAt", "amazon", "B1", 1299, 4.1),
        ("Samsung Galaxy Buds 2 Pro Earbuds with Mic", "Samsung", "amazon", "S1", 12999, 4.4),
        ("Sony WH-1000XM5 Wireless Noise Cancellation Headset", "Sony", "amazon", "SO1", 26990, 4.5),
        ("Sony WH-1000XM4 Bluetooth Noise Cancellation Headset", "Sony", "flipkart", "SO2", 21990, 4.4),
        ("Apple iPhone 15 (128 GB) Blue", "Apple", "amazon", "AP1", 66999, 4.6),
        ("Apple iPhone 15 (128 GB) + AirPods Combo", "Apple", "flipkart", "AP2", 74999, 4.5),
        ("Mi Smart Band 7 Fitness Tracker", "Mi", "flipkart", "MI1", 2799, 4.3),
        ("Logitech MX Master 3S Wireless Mouse", "Logitech", "amazon", "LO1", 8995, 4.7),
        ("Lenovo IdeaPad Slim 3 Intel Core i5 Laptop", "Lenovo", "flipkart", "LE1", 54990, 4.2),
        ("Cetaphil Gentle Skin Cleanser 250ml", "Cetaphil", "amazon", "CE1", 499, 4.6),
        ("Lakme Absolute 3D Smooth Matte Foundation 25g", "Lakme", "amazon", "LA1", 1199, 4.2),
        ("Mamaearth Vitamin C Face Wash", "Mamaearth", "nykaa", "MA1", 249, 4.4),
        ("Plum Green Tea Toner with Witch Hazel", "Plum", "nykaa", "PL1", 390, 4.5),
    ]
    for canonical_title, brand, platform, pid, price, rating in rows:
        product = Product(canonical_title=canonical_title, brand=brand)
        db.add(product)
        db.flush()
        db.add(
            Listing(
                product_id=product.id,
                platform=platform,
                platform_product_id=pid,
                raw_title=canonical_title,
                price=Decimal(str(price)),
                rating=Decimal(str(rating)),
                url=f"https://{platform}.example/{pid}",
                last_seen_at=datetime.now(timezone.utc),
            )
        )
    db.commit()


@pytest.fixture()
def seeded_catalog(db_session):
    reset_provider_cache()
    _seed_catalog(db_session)
    reindex_products(db_session)
    yield db_session
    reset_provider_cache()


def test_ranking_quality_meets_thresholds(seeded_catalog):
    settings = get_settings()
    report = evaluate(seeded_catalog, page_size=10)
    summary = report.as_dict()["summary"]

    assert summary["ndcg_at_5"] >= settings.eval_min_ndcg_at_5, (
        f"NDCG@5 regression: {summary['ndcg_at_5']} < {settings.eval_min_ndcg_at_5}\n"
        f"Per-query: {report.as_dict()['cases']}"
    )
    assert summary["precision_at_3"] >= settings.eval_min_precision_at_3, (
        f"Precision@3 regression: {summary['precision_at_3']} < "
        f"{settings.eval_min_precision_at_3}\n"
        f"Per-query: {report.as_dict()['cases']}"
    )
