"""End-to-end test of the /search API against an in-memory SQLite DB.

The whole app is wired up: lifespan events run, the scheduler is disabled by
the env vars set in conftest, and we override the DB dependency to point at
a fresh in-memory engine per test.

For semantic-mode tests we also build the embedding index against the same
session so the API has vectors to compare against.
"""
from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.embeddings import reindex_products, reset_provider_cache
from app.main import app
from app.models import Product


def _seed_products(db) -> None:
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


def _build_client(*, with_index: bool):
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
        _seed_products(db)
        if with_index:
            reindex_products(db)

    return engine, TestClient(app)


@pytest.fixture(autouse=True)
def _reset_embedding_cache():
    # The provider is process-cached; reset between tests so settings overrides
    # (and a fresh in-memory DB) don't bleed across cases.
    reset_provider_cache()
    yield
    reset_provider_cache()


@pytest.fixture()
def client():
    engine, c = _build_client(with_index=False)
    with c:
        yield c
    app.dependency_overrides.clear()
    engine.dispose()


@pytest.fixture()
def semantic_client():
    engine, c = _build_client(with_index=True)
    with c:
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


# --- Phase 2 ---------------------------------------------------------------


def test_keyword_mode_returns_keyword_effective_mode(client):
    body = client.get("/search", params={"q": "earbuds", "mode": "keyword"}).json()
    assert body["mode"] == "keyword"
    assert body["effective_mode"] == "keyword"


def test_semantic_mode_falls_back_when_index_empty(client):
    """Edge case 5.1 — cold start. Semantic falls back to keyword search."""
    body = client.get("/search", params={"q": "earbuds", "mode": "semantic"}).json()
    assert body["mode"] == "semantic"
    assert body["effective_mode"] == "keyword"
    assert any("vector index empty" in n for n in body["notes"])


def test_semantic_mode_runs_when_index_built(semantic_client):
    body = semantic_client.get("/search", params={"q": "earbuds", "mode": "semantic"}).json()
    assert body["mode"] == "semantic"
    assert body["effective_mode"] == "semantic"
    assert body["total"] >= 1
    # The Airdopes product should rank near the top for an earbuds query.
    titles = [r["title"] for r in body["results"]]
    assert any("Airdopes" in t for t in titles)


def test_natural_language_price_filter_parsed(semantic_client):
    """Edge case 4.5 — `under 2000` is lifted into max_price."""
    body = semantic_client.get(
        "/search", params={"q": "earbuds under 2000", "mode": "semantic"}
    ).json()
    assert "earbuds" in body["parsed_residual"].lower()
    assert "2000" not in body["parsed_residual"]
    # The iPhone (₹66,999) and the Sony (₹26,990) must not appear.
    asins = {r["platform_product_id"] for r in body["results"]}
    assert "B03" not in asins
    assert "B01" not in asins


def test_explicit_filter_overrides_parsed(semantic_client):
    """If the caller passes max_price, parser should not relax it."""
    body = semantic_client.get(
        "/search",
        params={"q": "earbuds under 5000", "max_price": 1000, "mode": "semantic"},
    ).json()
    # max_price=1000 is more restrictive than the parsed 5000 — no products match.
    asins = {r["platform_product_id"] for r in body["results"]}
    assert "B02" not in asins  # boAt is 1299


def test_hybrid_mode_includes_keyword_hits(semantic_client):
    body = semantic_client.get(
        "/search", params={"q": "iPhone", "mode": "hybrid"}
    ).json()
    assert body["mode"] == "hybrid"
    titles = [r["title"] for r in body["results"]]
    assert any("iPhone" in t for t in titles)


def test_search_results_include_score_and_similarity(semantic_client):
    body = semantic_client.get(
        "/search", params={"q": "headphones", "mode": "semantic"}
    ).json()
    assert body["results"], "expected at least one hit"
    first = body["results"][0]
    assert "score" in first
    assert "similarity" in first
    assert 0.0 <= first["similarity"] <= 1.0


def test_invalid_mode_rejected(client):
    response = client.get("/search", params={"q": "x", "mode": "bogus"})
    assert response.status_code == 422


def test_empty_query_returns_curated_with_note(client):
    body = client.get("/search").json()
    assert body["total"] == 3
    assert any("trending" in n for n in body["notes"])
