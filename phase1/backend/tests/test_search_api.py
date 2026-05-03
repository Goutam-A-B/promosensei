"""End-to-end test of the /search API against an in-memory SQLite DB.

The whole app is wired up: lifespan events run, the scheduler is disabled by
the env vars set in conftest, and we override the DB dependency to point at
a fresh in-memory engine per test.
"""
from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models import Product


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

    # Seed
    with Session() as db:
        db.add_all(
            [
                Product(
                    platform="amazon",
                    platform_product_id="B01",
                    title="Sony WH-1000XM5 Wireless Headphones",
                    price=Decimal("26990.00"),
                    original_price=Decimal("34990.00"),
                    discount=Decimal("22.86"),
                    rating=Decimal("4.5"),
                    url="https://www.amazon.in/dp/B01",
                ),
                Product(
                    platform="amazon",
                    platform_product_id="B02",
                    title="boAt Airdopes 141 Bluetooth Earbuds",
                    price=Decimal("1299.00"),
                    original_price=Decimal("2990.00"),
                    discount=Decimal("56.55"),
                    rating=Decimal("4.1"),
                    url="https://www.amazon.in/dp/B02",
                ),
                Product(
                    platform="amazon",
                    platform_product_id="B03",
                    title="Apple iPhone 15 (128 GB) Blue",
                    price=Decimal("66999.00"),
                    rating=Decimal("4.6"),
                    url="https://www.amazon.in/dp/B03",
                ),
            ]
        )
        db.commit()

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()
    engine.dispose()


def test_health(client):
    assert client.get("/health").status_code == 200


def test_empty_query_returns_all(client):
    response = client.get("/search")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert len(body["results"]) == 3


def test_keyword_match(client):
    response = client.get("/search", params={"q": "earbuds"})
    body = response.json()
    assert body["total"] == 1
    assert "Airdopes" in body["results"][0]["title"]


def test_multi_token_query_is_and(client):
    response = client.get("/search", params={"q": "Sony Headphones"})
    body = response.json()
    assert body["total"] == 1


def test_price_filter(client):
    response = client.get("/search", params={"max_price": 5000})
    body = response.json()
    assert body["total"] == 1
    assert body["results"][0]["platform_product_id"] == "B02"


def test_sort_price_asc(client):
    response = client.get("/search", params={"sort": "price_asc"})
    titles = [r["title"] for r in response.json()["results"]]
    assert "Airdopes" in titles[0]


def test_pagination(client):
    response = client.get("/search", params={"page": 1, "page_size": 2})
    body = response.json()
    assert body["page_size"] == 2
    assert len(body["results"]) == 2
    assert body["total"] == 3
