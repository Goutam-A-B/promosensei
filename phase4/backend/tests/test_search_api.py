"""End-to-end test of the /search API against an in-memory SQLite DB.

Phase 3 returns *grouped* products: each card carries its per-platform
listings. The seed below intentionally creates one cross-platform cluster
(Sony WH-1000XM5 on Amazon + Flipkart) so we can assert the grouping
behavior without depending on the full matcher.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.embeddings import reindex_products, reset_provider_cache
from app.main import app
from app.models import Listing, Product


def _add_product(
    db,
    *,
    canonical_title: str,
    brand: str | None,
    listings: list[dict],
    model_number: str | None = None,
) -> None:
    product = Product(
        canonical_title=canonical_title,
        brand=brand,
        model_number=model_number,
    )
    db.add(product)
    db.flush()
    for spec in listings:
        db.add(
            Listing(
                product_id=product.id,
                platform=spec["platform"],
                platform_product_id=spec["pid"],
                raw_title=spec.get("raw_title", canonical_title),
                price=Decimal(str(spec["price"])),
                original_price=Decimal(str(spec["original_price"]))
                if spec.get("original_price") is not None
                else None,
                discount=Decimal(str(spec["discount"])) if spec.get("discount") is not None else None,
                rating=Decimal(str(spec["rating"])) if spec.get("rating") is not None else None,
                url=spec.get("url", f"https://{spec['platform']}.example/{spec['pid']}"),
                image_url=spec.get("image_url"),
                last_seen_at=datetime.now(timezone.utc),
            )
        )


def _seed(db) -> None:
    # Clustered: same product on two platforms.
    _add_product(
        db,
        canonical_title="Sony WH-1000XM5 Wireless Headphones",
        brand="Sony",
        model_number="WH-1000XM5",
        listings=[
            dict(
                platform="amazon", pid="B0CHX1W1XY", price="26990",
                original_price="34990", discount="22.86", rating="4.5",
                raw_title="Sony WH-1000XM5 Wireless Noise Cancelling Headphones",
            ),
            dict(
                platform="flipkart", pid="ACCKT8UFPEZ6GXHZ", price="25990",
                original_price="34990", discount="25.72", rating="4.4",
                raw_title="Sony WH1000XM5 Active Noise Cancellation Bluetooth Headset",
            ),
        ],
    )
    _add_product(
        db,
        canonical_title="boAt Airdopes 141 Bluetooth Earbuds",
        brand="boAt",
        listings=[
            dict(
                platform="amazon", pid="B09G9HD6PD", price="1299",
                original_price="2990", discount="56.55", rating="4.1",
                raw_title="boAt Airdopes 141 Bluetooth Truly Wireless Earbuds with Mic",
            )
        ],
    )
    _add_product(
        db,
        canonical_title="Apple iPhone 15 (128 GB) Blue",
        brand="Apple",
        listings=[
            dict(platform="amazon", pid="B0BDHWDR12", price="66999", rating="4.6")
        ],
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
        _seed(db)
        if with_index:
            reindex_products(db)

    return engine, TestClient(app)


@pytest.fixture(autouse=True)
def _reset_embedding_cache():
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


# --- Liveness / shape ------------------------------------------------------


def test_health(client):
    assert client.get("/health").status_code == 200


def test_grouped_response_shape(client):
    body = client.get("/search").json()
    assert body["total"] == 3
    sony = next(r for r in body["results"] if r["brand"] == "Sony")
    assert sony["canonical_title"].startswith("Sony WH-1000XM5")
    assert sony["platform_count"] == 2
    platforms = {l["platform"] for l in sony["listings"]}
    assert platforms == {"amazon", "flipkart"}
    # Cheapest first inside the group.
    prices = [Decimal(l["price"]) for l in sony["listings"]]
    assert prices == sorted(prices)


def test_best_price_is_min_across_platforms(client):
    body = client.get("/search").json()
    sony = next(r for r in body["results"] if r["brand"] == "Sony")
    assert Decimal(sony["best_price"]) == Decimal("25990.00")
    assert sony["best_platform"] == "flipkart"


# --- Keyword behaviour -----------------------------------------------------


def test_keyword_match_canonical_title(client):
    body = client.get("/search", params={"q": "earbuds"}).json()
    assert body["total"] == 1
    assert "Airdopes" in body["results"][0]["canonical_title"]


def test_keyword_match_listing_title_only(client):
    """Listing.raw_title differs from canonical_title — keyword should still hit."""
    body = client.get("/search", params={"q": "Cancellation"}).json()
    assert body["total"] == 1
    assert body["results"][0]["brand"] == "Sony"


def test_multi_token_query_is_and(client):
    body = client.get("/search", params={"q": "Sony Headphones"}).json()
    assert body["total"] == 1


def test_pagination(client):
    body = client.get("/search", params={"page": 1, "page_size": 2}).json()
    assert body["page_size"] == 2
    assert len(body["results"]) == 2
    assert body["total"] == 3


# --- Filters ---------------------------------------------------------------


def test_max_price_keeps_only_cheap_listings(client):
    body = client.get("/search", params={"max_price": 5000}).json()
    assert body["total"] == 1
    assert body["results"][0]["brand"] == "boAt"


def test_max_price_keeps_product_when_one_listing_qualifies(client):
    """Sony's Flipkart listing (25,990) qualifies under 26,000 — show only it."""
    body = client.get("/search", params={"max_price": 26000}).json()
    sony = next((r for r in body["results"] if r["brand"] == "Sony"), None)
    assert sony is not None, "Sony should survive — Flipkart listing fits"
    platforms = {l["platform"] for l in sony["listings"]}
    assert platforms == {"flipkart"}, "Amazon listing should be dropped"


def test_platform_filter(client):
    body = client.get("/search", params={"platform": "flipkart"}).json()
    # Only Sony has a flipkart listing.
    assert body["total"] == 1
    assert body["results"][0]["brand"] == "Sony"
    assert {l["platform"] for l in body["results"][0]["listings"]} == {"flipkart"}


def test_sort_price_asc(client):
    titles = [r["canonical_title"] for r in client.get("/search", params={"sort": "price_asc"}).json()["results"]]
    assert "Airdopes" in titles[0]


# --- Modes / semantic -------------------------------------------------------


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
    titles = [r["canonical_title"] for r in body["results"]]
    assert any("Airdopes" in t for t in titles)


def test_natural_language_price_filter_parsed(semantic_client):
    """Edge case 4.5 — `under 2000` is lifted into max_price."""
    body = semantic_client.get(
        "/search", params={"q": "earbuds under 2000", "mode": "semantic"}
    ).json()
    assert "earbuds" in body["parsed_residual"].lower()
    assert "2000" not in body["parsed_residual"]
    brands = {r["brand"] for r in body["results"]}
    assert "Apple" not in brands
    assert "Sony" not in brands


def test_explicit_filter_overrides_parsed(semantic_client):
    body = semantic_client.get(
        "/search",
        params={"q": "earbuds under 5000", "max_price": 1000, "mode": "semantic"},
    ).json()
    brands = {r["brand"] for r in body["results"]}
    assert "boAt" not in brands  # 1299 > 1000


def test_hybrid_mode_includes_keyword_hits(semantic_client):
    body = semantic_client.get(
        "/search", params={"q": "iPhone", "mode": "hybrid"}
    ).json()
    assert body["mode"] == "hybrid"
    titles = [r["canonical_title"] for r in body["results"]]
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
