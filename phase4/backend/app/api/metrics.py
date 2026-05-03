"""GET /metrics — Prometheus text-format scrape target."""
from fastapi import APIRouter, Response

from app.cache import get_cache
from app.config import get_settings
from app.observability import render_prometheus
from app.observability.metrics import METRICS

router = APIRouter()


@router.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    settings = get_settings()
    if not settings.metrics_enabled:
        return Response(status_code=404)

    # Refresh the cache size gauge from the live cache stats so /metrics
    # shows current depth without us having to hook every set/invalidate.
    stats = get_cache().stats()
    gauge = METRICS.gauge("promosensei_cache_entries", "Approximate cache entry count.")
    gauge.set(float(stats.get("size", 0)))
    hits_gauge = METRICS.gauge("promosensei_cache_hits_total_snapshot", "Cumulative cache hits.")
    hits_gauge.set(float(stats.get("hits", 0)))
    misses_gauge = METRICS.gauge("promosensei_cache_misses_total_snapshot", "Cumulative cache misses.")
    misses_gauge.set(float(stats.get("misses", 0)))

    body = render_prometheus()
    return Response(content=body, media_type="text/plain; version=0.0.4; charset=utf-8")
