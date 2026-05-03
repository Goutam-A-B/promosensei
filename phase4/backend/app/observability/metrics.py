"""Hand-rolled Prometheus-compatible metrics registry.

The wire format is the standard text exposition that any Prometheus
scraper understands, so the API doesn't tie itself to `prometheus_client`
just to count a handful of things.

Three primitive types:

- `Counter` — monotonically increasing total, partitioned by labels.
- `Histogram` — bucketed counts plus a sum, used for latency.
- `Gauge` — current value (used for circuit-breaker state).

The public surface is the `record_*` helpers; the underlying registry
lives in `METRICS` for /metrics to render.

Thread-safety: writes acquire a per-metric lock. The hot path is short
enough that contention isn't worth optimising further at this scale.
"""
from __future__ import annotations

import threading
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable

# Default histogram buckets in milliseconds — picked to match the Phase 4
# latency targets (cached < 300, cold < 800).
DEFAULT_LATENCY_BUCKETS_MS: tuple[float, ...] = (
    5, 10, 25, 50, 100, 200, 300, 500, 800, 1500, 3000, 8000,
)


def _label_signature(labels: dict[str, str]) -> tuple[tuple[str, str], ...]:
    return tuple(sorted(labels.items()))


def _format_labels(sig: tuple[tuple[str, str], ...]) -> str:
    if not sig:
        return ""
    parts = [f'{k}="{_escape(v)}"' for k, v in sig]
    return "{" + ",".join(parts) + "}"


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


@dataclass
class Counter:
    name: str
    help_text: str
    values: dict[tuple[tuple[str, str], ...], float] = field(default_factory=lambda: defaultdict(float))
    lock: threading.Lock = field(default_factory=threading.Lock)

    def inc(self, amount: float = 1.0, **labels: str) -> None:
        sig = _label_signature(labels)
        with self.lock:
            self.values[sig] += amount

    def render(self) -> Iterable[str]:
        yield f"# HELP {self.name} {self.help_text}"
        yield f"# TYPE {self.name} counter"
        for sig, value in sorted(self.values.items()):
            yield f"{self.name}{_format_labels(sig)} {value}"


@dataclass
class Gauge:
    name: str
    help_text: str
    values: dict[tuple[tuple[str, str], ...], float] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def set(self, value: float, **labels: str) -> None:
        sig = _label_signature(labels)
        with self.lock:
            self.values[sig] = value

    def render(self) -> Iterable[str]:
        yield f"# HELP {self.name} {self.help_text}"
        yield f"# TYPE {self.name} gauge"
        for sig, value in sorted(self.values.items()):
            yield f"{self.name}{_format_labels(sig)} {value}"


@dataclass
class Histogram:
    name: str
    help_text: str
    buckets: tuple[float, ...] = DEFAULT_LATENCY_BUCKETS_MS
    counts: dict[tuple[tuple[str, str], ...], list[int]] = field(default_factory=dict)
    sums: dict[tuple[tuple[str, str], ...], float] = field(default_factory=lambda: defaultdict(float))
    totals: dict[tuple[tuple[str, str], ...], int] = field(default_factory=lambda: defaultdict(int))
    lock: threading.Lock = field(default_factory=threading.Lock)

    def observe(self, value: float, **labels: str) -> None:
        sig = _label_signature(labels)
        with self.lock:
            bucket_counts = self.counts.setdefault(sig, [0] * len(self.buckets))
            for i, edge in enumerate(self.buckets):
                if value <= edge:
                    bucket_counts[i] += 1
            self.sums[sig] += value
            self.totals[sig] += 1

    def render(self) -> Iterable[str]:
        yield f"# HELP {self.name} {self.help_text}"
        yield f"# TYPE {self.name} histogram"
        for sig in sorted(self.counts.keys()):
            cumulative = 0
            for i, edge in enumerate(self.buckets):
                cumulative = self.counts[sig][i]
                bucket_labels = sig + (("le", str(edge)),)
                yield f"{self.name}_bucket{_format_labels(bucket_labels)} {cumulative}"
            inf_labels = sig + (("le", "+Inf"),)
            yield f"{self.name}_bucket{_format_labels(inf_labels)} {self.totals[sig]}"
            yield f"{self.name}_sum{_format_labels(sig)} {self.sums[sig]}"
            yield f"{self.name}_count{_format_labels(sig)} {self.totals[sig]}"


@dataclass
class Registry:
    counters: dict[str, Counter] = field(default_factory=dict)
    gauges: dict[str, Gauge] = field(default_factory=dict)
    histograms: dict[str, Histogram] = field(default_factory=dict)

    def counter(self, name: str, help_text: str) -> Counter:
        if name not in self.counters:
            self.counters[name] = Counter(name=name, help_text=help_text)
        return self.counters[name]

    def gauge(self, name: str, help_text: str) -> Gauge:
        if name not in self.gauges:
            self.gauges[name] = Gauge(name=name, help_text=help_text)
        return self.gauges[name]

    def histogram(self, name: str, help_text: str, buckets: tuple[float, ...] = DEFAULT_LATENCY_BUCKETS_MS) -> Histogram:
        if name not in self.histograms:
            self.histograms[name] = Histogram(name=name, help_text=help_text, buckets=buckets)
        return self.histograms[name]


# ---- Module-level registry + helpers --------------------------------------

METRICS = Registry()

_search_latency = METRICS.histogram(
    "promosensei_search_latency_ms",
    "End-to-end /search latency in milliseconds.",
)
_cache_events = METRICS.counter(
    "promosensei_cache_events_total",
    "Cache hits and misses, partitioned by namespace.",
)
_scrape_outcomes = METRICS.counter(
    "promosensei_scrape_outcomes_total",
    "Per-platform scrape outcome (status: ok|partial|failed).",
)
_price_refreshes = METRICS.counter(
    "promosensei_price_refresh_total",
    "Listings touched by the incremental price refresher.",
)
_breaker_state = METRICS.gauge(
    "promosensei_circuit_breaker_state",
    "Circuit-breaker state: 0=closed, 1=half_open, 2=open.",
)


def record_search_latency(*, mode: str, cached: bool, latency_ms: float) -> None:
    _search_latency.observe(latency_ms, mode=mode, cached=str(cached).lower())


def record_cache_hit(namespace: str) -> None:
    _cache_events.inc(namespace=namespace, event="hit")


def record_cache_miss(namespace: str) -> None:
    _cache_events.inc(namespace=namespace, event="miss")


def record_scrape_outcome(*, platform: str, status: str, count: int = 1) -> None:
    _scrape_outcomes.inc(amount=count, platform=platform, status=status)


def record_price_refresh(*, platform: str, updated: int, errors: int) -> None:
    if updated:
        _price_refreshes.inc(amount=updated, platform=platform, outcome="updated")
    if errors:
        _price_refreshes.inc(amount=errors, platform=platform, outcome="error")


_BREAKER_STATE_VALUES = {"closed": 0.0, "half_open": 1.0, "open": 2.0}


def record_circuit_breaker_state(*, name: str, state: str) -> None:
    value = _BREAKER_STATE_VALUES.get(state, -1.0)
    _breaker_state.set(value, name=name)


def render_prometheus() -> str:
    """Return the full registry serialized in Prometheus text format."""
    lines: list[str] = []
    for counter in METRICS.counters.values():
        lines.extend(counter.render())
    for gauge in METRICS.gauges.values():
        lines.extend(gauge.render())
    for histogram in METRICS.histograms.values():
        lines.extend(histogram.render())
    return "\n".join(lines) + "\n"


def reset_metrics_for_tests() -> None:
    """Clear every counter/gauge/histogram. Tests only — never call from app code."""
    for counter in METRICS.counters.values():
        with counter.lock:
            counter.values.clear()
    for gauge in METRICS.gauges.values():
        with gauge.lock:
            gauge.values.clear()
    for histogram in METRICS.histograms.values():
        with histogram.lock:
            histogram.counts.clear()
            histogram.sums.clear()
            histogram.totals.clear()
