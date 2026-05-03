"""Tests for the /health/scrapers endpoint.

Exercises the per-platform success-rate aggregation and ensures all three
tracked platforms always appear (even with no runs yet) so the UI can
distinguish "no data" from "down".
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.embeddings import reset_provider_cache
from app.main import app
from app.models import Listing, Product, ScraperRun


def _build_client():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return engine, Session, TestClient(app)


@pytest.fixture(autouse=True)
def _reset_embedding_cache():
    reset_provider_cache()
    yield
    reset_provider_cache()


@pytest.fixture()
def client_factory():
    created = []

    def _make():
        engine, Session, c = _build_client()
        created.append((engine, c))
        return Session, c

    yield _make
    app.dependency_overrides.clear()
    for engine, c in created:
        c.close()
        engine.dispose()


def test_empty_db_lists_all_platforms_with_no_data(client_factory):
    _, client = client_factory()
    body = client.get("/health/scrapers").json()
    platforms = {s["platform"] for s in body["scrapers"]}
    assert platforms == {"amazon", "flipkart", "nykaa"}
    for s in body["scrapers"]:
        assert s["runs_30d"] == 0
        assert s["success_rate_30d"] == 0.0
        assert s["last_status"] is None


def test_success_rate_window(client_factory):
    Session, client = client_factory()
    now = datetime.now(timezone.utc)
    with Session() as db:
        db.add_all(
            [
                ScraperRun(
                    platform="amazon",
                    started_at=now - timedelta(days=1),
                    finished_at=now - timedelta(days=1),
                    status="ok",
                    inserted=10,
                ),
                ScraperRun(
                    platform="amazon",
                    started_at=now - timedelta(hours=2),
                    finished_at=now - timedelta(hours=2),
                    status="failed",
                    error_message="403 from Amazon",
                ),
                # Outside the window — should not affect the rate.
                ScraperRun(
                    platform="amazon",
                    started_at=now - timedelta(days=60),
                    finished_at=now - timedelta(days=60),
                    status="failed",
                ),
            ]
        )
        db.commit()

    body = client.get("/health/scrapers").json()
    amazon = next(s for s in body["scrapers"] if s["platform"] == "amazon")
    assert amazon["runs_30d"] == 2
    assert amazon["success_rate_30d"] == 0.5
    assert amazon["last_status"] == "failed"
    assert "403" in (amazon["last_error"] or "")


def test_listing_count_per_platform(client_factory):
    Session, client = client_factory()
    with Session() as db:
        product = Product(canonical_title="Sony WH-1000XM5", brand="Sony")
        db.add(product)
        db.flush()
        db.add_all(
            [
                Listing(
                    product_id=product.id,
                    platform="amazon",
                    platform_product_id="B01",
                    raw_title="Sony WH-1000XM5",
                    price=Decimal("26990"),
                    url="https://www.amazon.in/dp/B01",
                ),
                Listing(
                    product_id=product.id,
                    platform="flipkart",
                    platform_product_id="FK01",
                    raw_title="Sony WH1000XM5",
                    price=Decimal("25990"),
                    url="https://www.flipkart.com/p/FK01",
                ),
            ]
        )
        db.commit()

    body = client.get("/health/scrapers").json()
    counts = {s["platform"]: s["listings_count"] for s in body["scrapers"]}
    assert counts["amazon"] == 1
    assert counts["flipkart"] == 1
    assert counts["nykaa"] == 0
