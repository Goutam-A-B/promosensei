"""Tests for the incremental product-embedding indexer.

Covers edge case 5.3 (re-embed when title changes) and 5.2 (vectors are
keyed by model_id so multiple model versions can coexist).
"""
from __future__ import annotations

import json
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.embeddings.hashing import HashingEmbeddingProvider
from app.embeddings.indexer import reindex_products, title_hash
from app.models import Product, ProductEmbedding


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _seed(db, *titles):
    for i, title in enumerate(titles, start=1):
        db.add(
            Product(
                platform="amazon",
                platform_product_id=f"B{i:09d}",
                title=title,
                price=Decimal("999.00"),
                url=f"https://www.amazon.in/dp/B{i:09d}",
            )
        )
    db.commit()


def _provider(dim: int = 64, model_id: str = "test-v1") -> HashingEmbeddingProvider:
    return HashingEmbeddingProvider(dim=dim, model_id=model_id)


class TestIndexerBasic:
    def test_embeds_all_new_products(self, db_session):
        _seed(db_session, "Sony Headphones", "boAt Earbuds", "Apple iPhone 15")
        provider = _provider()

        stats = reindex_products(db_session, provider=provider)

        assert stats.embedded == 3
        assert stats.refreshed == 0
        assert stats.skipped == 0

        rows = db_session.scalars(select(ProductEmbedding)).all()
        assert len(rows) == 3
        assert all(r.model_id == provider.model_id for r in rows)
        assert all(r.dim == provider.dim for r in rows)
        # Vectors are valid JSON of the right length.
        for r in rows:
            vec = json.loads(r.vector_json)
            assert len(vec) == provider.dim

    def test_second_run_is_a_noop(self, db_session):
        _seed(db_session, "Sony Headphones", "boAt Earbuds")
        provider = _provider()
        reindex_products(db_session, provider=provider)
        stats = reindex_products(db_session, provider=provider)
        assert stats.embedded == 0
        assert stats.refreshed == 0
        assert stats.skipped == 2

    def test_title_change_triggers_refresh(self, db_session):
        """Edge case 5.3 — stale embedding after product update."""
        _seed(db_session, "Sony Headphones")
        provider = _provider()
        reindex_products(db_session, provider=provider)

        product = db_session.scalars(select(Product)).one()
        product.title = "Sony WH-1000XM5 Headphones"
        db_session.commit()

        stats = reindex_products(db_session, provider=provider)
        assert stats.embedded == 0
        assert stats.refreshed == 1

        embedding = db_session.scalars(select(ProductEmbedding)).one()
        assert embedding.title_hash == title_hash("Sony WH-1000XM5 Headphones")

    def test_product_title_hash_kept_in_sync(self, db_session):
        _seed(db_session, "Sony Headphones")
        provider = _provider()
        reindex_products(db_session, provider=provider)
        product = db_session.scalars(select(Product)).one()
        assert product.title_hash == title_hash("Sony Headphones")


class TestIndexerModelIsolation:
    def test_two_models_keep_separate_vectors(self, db_session):
        """Edge case 5.2 — never mix vectors of different models."""
        _seed(db_session, "Sony Headphones", "boAt Earbuds")

        v1 = HashingEmbeddingProvider(dim=64, model_id="v1")
        v2 = HashingEmbeddingProvider(dim=128, model_id="v2")

        reindex_products(db_session, provider=v1)
        reindex_products(db_session, provider=v2)

        rows = db_session.scalars(select(ProductEmbedding)).all()
        models = {r.model_id for r in rows}
        assert models == {v1.model_id, v2.model_id}
        assert len(rows) == 4  # 2 products × 2 models


class TestIndexerLimit:
    def test_limit_only_processes_subset(self, db_session):
        _seed(db_session, "a", "b", "c", "d")
        provider = _provider()
        stats = reindex_products(db_session, provider=provider, limit=2)
        assert stats.embedded == 2
        assert db_session.scalar(select(ProductEmbedding.id).limit(1)) is not None
