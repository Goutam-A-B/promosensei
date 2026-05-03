"""Structured logging + metrics registry."""
from __future__ import annotations

import json
import logging

import pytest

from app.observability import (
    record_cache_hit,
    record_cache_miss,
    record_circuit_breaker_state,
    record_search_latency,
    render_prometheus,
    reset_metrics_for_tests,
    setup_logging,
)
from app.observability.logging import JsonFormatter


# ---- JSON log formatting --------------------------------------------------


def test_json_formatter_emits_required_fields():
    record = logging.LogRecord(
        name="app.test",
        level=logging.INFO,
        pathname="x.py",
        lineno=1,
        msg="hello %s",
        args=("world",),
        exc_info=None,
    )
    line = JsonFormatter().format(record)
    payload = json.loads(line)
    assert payload["level"] == "INFO"
    assert payload["logger"] == "app.test"
    assert payload["message"] == "hello world"
    assert "ts" in payload


def test_json_formatter_includes_extra_fields():
    record = logging.LogRecord(
        name="app.test",
        level=logging.INFO,
        pathname="x.py",
        lineno=1,
        msg="x",
        args=(),
        exc_info=None,
    )
    record.platform = "amazon"
    record.count = 12
    payload = json.loads(JsonFormatter().format(record))
    assert payload["platform"] == "amazon"
    assert payload["count"] == 12


def test_json_formatter_repr_unserialisable_extras():
    """Non-JSON-able values shouldn't blow up the formatter."""
    record = logging.LogRecord(
        name="app.test", level=logging.INFO, pathname="x.py", lineno=1,
        msg="x", args=(), exc_info=None,
    )

    class Weird:
        def __repr__(self) -> str:
            return "<weird>"

    record.thing = Weird()
    payload = json.loads(JsonFormatter().format(record))
    assert payload["thing"] == "<weird>"


def test_setup_logging_is_idempotent():
    setup_logging(level="DEBUG", fmt="json")
    handlers_after_first = len(logging.getLogger().handlers)
    setup_logging(level="DEBUG", fmt="json")
    handlers_after_second = len(logging.getLogger().handlers)
    assert handlers_after_first == handlers_after_second == 1


# ---- Metrics primitives ---------------------------------------------------


def test_counter_records_and_renders():
    reset_metrics_for_tests()
    record_cache_hit("search")
    record_cache_hit("search")
    record_cache_miss("search")
    out = render_prometheus()
    assert "promosensei_cache_events_total" in out
    assert 'event="hit"' in out
    assert 'event="miss"' in out


def test_histogram_records_buckets():
    reset_metrics_for_tests()
    record_search_latency(mode="hybrid", cached=False, latency_ms=120.0)
    record_search_latency(mode="hybrid", cached=False, latency_ms=750.0)
    out = render_prometheus()
    assert "promosensei_search_latency_ms_bucket" in out
    assert "promosensei_search_latency_ms_sum" in out
    assert "promosensei_search_latency_ms_count" in out
    assert 'le="100"' in out
    assert 'le="+Inf"' in out


def test_gauge_records_breaker_state():
    reset_metrics_for_tests()
    record_circuit_breaker_state(name="amazon", state="open")
    out = render_prometheus()
    assert 'promosensei_circuit_breaker_state{name="amazon"} 2.0' in out


def test_render_format_includes_help_and_type_lines():
    reset_metrics_for_tests()
    record_cache_hit("search")
    out = render_prometheus()
    assert "# HELP promosensei_cache_events_total" in out
    assert "# TYPE promosensei_cache_events_total counter" in out


def test_reset_metrics_zeroes_everything():
    record_cache_hit("search")
    record_search_latency(mode="hybrid", cached=False, latency_ms=200.0)
    reset_metrics_for_tests()
    out = render_prometheus()
    # Headers stay, but no data lines should remain.
    assert 'event="hit"' not in out
    assert "promosensei_search_latency_ms_count" not in out
