"""Phase 4 observability surface.

Two narrow APIs that the rest of the app talks to:

- `setup_logging()` configures structured JSON logs (or plain text) once
  at process start.
- `metrics` exposes a small bag of counters/histograms plus a Prometheus
  text-format renderer used by `/metrics`.

Kept hand-rolled rather than pulling in `prometheus_client` because the
rest of the project leans on small, vendor-free building blocks. Swap in
the upstream client when scale demands it — the public surface is the
same `record_*` calls.
"""
from app.observability.logging import setup_logging
from app.observability.metrics import (
    METRICS,
    record_cache_hit,
    record_cache_miss,
    record_circuit_breaker_state,
    record_price_refresh,
    record_scrape_outcome,
    record_search_latency,
    render_prometheus,
    reset_metrics_for_tests,
)

__all__ = [
    "METRICS",
    "record_cache_hit",
    "record_cache_miss",
    "record_circuit_breaker_state",
    "record_price_refresh",
    "record_scrape_outcome",
    "record_search_latency",
    "render_prometheus",
    "reset_metrics_for_tests",
    "setup_logging",
]
