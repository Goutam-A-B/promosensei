"""GET /metrics — exposition format + cache-stat surfacing."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.cache import get_cache
from app.db import Base, get_db
from app.main import app
from app.observability import (
    record_cache_hit,
    record_search_latency,
)


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
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    engine.dispose()


def test_metrics_endpoint_returns_prometheus_text(client):
    record_cache_hit("search")
    record_search_latency(mode="hybrid", cached=True, latency_ms=42.0)
    response = client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    body = response.text
    assert "# HELP " in body
    assert "# TYPE " in body
    assert "promosensei_cache_events_total" in body
    assert "promosensei_search_latency_ms_bucket" in body


def test_metrics_endpoint_surfaces_cache_size(client):
    cache = get_cache()
    cache.set("k1", "v1", ttl_seconds=60)
    cache.set("k2", "v2", ttl_seconds=60)
    body = client.get("/metrics").text
    # Gauge updated on the /metrics fetch.
    assert "promosensei_cache_entries" in body


def test_metrics_endpoint_can_be_disabled(client, monkeypatch):
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "metrics_enabled", False)
    response = client.get("/metrics")
    assert response.status_code == 404
