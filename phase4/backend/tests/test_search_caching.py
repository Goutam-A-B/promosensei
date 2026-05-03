"""Verifies the /search cache fast-path actually hits."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.cache import get_cache
from app.db import Base, get_db
from app.main import app
from app.models import Listing, Product


def _seed(db) -> None:
    product = Product(canonical_title="boAt Airdopes 141", brand="boAt")
    db.add(product)
    db.flush()
    db.add(
        Listing(
            product_id=product.id,
            platform="amazon",
            platform_product_id="B1",
            raw_title="boAt Airdopes 141 Bluetooth Earbuds",
            price=Decimal("1299"),
            rating=Decimal("4.1"),
            url="https://amazon.in/b1",
            last_seen_at=datetime.now(timezone.utc),
        )
    )
    db.commit()


@pytest.fixture()
def client():
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
    with Session() as db:
        _seed(db)
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    engine.dispose()


def test_first_request_is_cold_second_is_warm(client):
    first = client.get("/search", params={"q": "earbuds", "mode": "keyword"}).json()
    second = client.get("/search", params={"q": "earbuds", "mode": "keyword"}).json()
    assert first["cache_hit"] is False
    assert second["cache_hit"] is True
    # Both must serve the same data.
    assert first["total"] == second["total"]
    assert [r["id"] for r in first["results"]] == [r["id"] for r in second["results"]]


def test_different_filters_do_not_collide(client):
    base = client.get("/search", params={"q": "earbuds", "mode": "keyword"}).json()
    other = client.get(
        "/search", params={"q": "earbuds", "mode": "keyword", "max_price": 100}
    ).json()
    # 100 is below all listings — we expect 0 results, not the cached `base`.
    assert other["cache_hit"] is False
    assert other["total"] == 0
    assert base["total"] >= 1


def test_response_carries_latency_ms(client):
    body = client.get("/search", params={"q": "earbuds", "mode": "keyword"}).json()
    assert "latency_ms" in body
    assert isinstance(body["latency_ms"], (int, float))
    assert body["latency_ms"] >= 0


def test_cache_invalidation_by_clear(client):
    client.get("/search", params={"q": "earbuds", "mode": "keyword"})
    get_cache().clear()
    body = client.get("/search", params={"q": "earbuds", "mode": "keyword"}).json()
    assert body["cache_hit"] is False
