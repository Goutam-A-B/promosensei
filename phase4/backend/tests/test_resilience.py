"""Retry-with-backoff + circuit breaker."""
from __future__ import annotations

import pytest

from app.resilience import (
    BreakerOpenError,
    CircuitBreaker,
    get_breaker,
    reset_breakers_for_tests,
    retry_with_backoff,
)


# ---- retry_with_backoff ---------------------------------------------------


def test_retry_returns_value_on_first_success():
    calls: list[int] = []

    def fn():
        calls.append(1)
        return "ok"

    assert retry_with_backoff(fn, attempts=3, base_delay=0, sleep=lambda _: None) == "ok"
    assert len(calls) == 1


def test_retry_eventually_succeeds():
    state = {"calls": 0}

    def fn():
        state["calls"] += 1
        if state["calls"] < 3:
            raise RuntimeError("flaky")
        return "ok"

    sleeps: list[float] = []
    result = retry_with_backoff(
        fn, attempts=5, base_delay=1.0, sleep=sleeps.append, rng=lambda: 1.0
    )
    assert result == "ok"
    assert state["calls"] == 3
    # Two sleeps before the third attempt — full-jitter * 1.0 == raw delay.
    assert sleeps == [1.0, 2.0]


def test_retry_raises_last_exception_when_attempts_exhausted():
    state = {"calls": 0}

    def fn():
        state["calls"] += 1
        raise ValueError(f"boom {state['calls']}")

    with pytest.raises(ValueError, match="boom 3"):
        retry_with_backoff(fn, attempts=3, base_delay=0, sleep=lambda _: None)
    assert state["calls"] == 3


def test_retry_caps_delay_at_max_delay():
    sleeps: list[float] = []

    def fn():
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        retry_with_backoff(
            fn,
            attempts=4,
            base_delay=10.0,
            max_delay=15.0,
            sleep=sleeps.append,
            rng=lambda: 1.0,
        )
    # Without cap: 10, 20, 40 — capped to 10, 15, 15.
    assert sleeps == [10.0, 15.0, 15.0]


def test_retry_invokes_on_attempt_callback():
    seen: list[tuple[int, str]] = []

    def fn():
        raise RuntimeError("nope")

    with pytest.raises(RuntimeError):
        retry_with_backoff(
            fn,
            attempts=2,
            base_delay=0,
            sleep=lambda _: None,
            on_attempt=lambda attempt, exc: seen.append((attempt, str(exc))),
        )
    assert seen == [(1, "nope"), (2, "nope")]


def test_retry_rejects_zero_attempts():
    with pytest.raises(ValueError):
        retry_with_backoff(lambda: None, attempts=0)


# ---- CircuitBreaker -------------------------------------------------------


def _make_breaker(*, threshold: int = 2, cooldown: float = 30.0):
    clock = [0.0]
    breaker = CircuitBreaker(
        "test",
        failure_threshold=threshold,
        cooldown_seconds=cooldown,
        clock=lambda: clock[0],
    )
    return breaker, clock


def test_breaker_starts_closed():
    breaker, _ = _make_breaker()
    assert breaker.state == "closed"


def test_breaker_passes_calls_through_when_closed():
    breaker, _ = _make_breaker()
    assert breaker.call(lambda: 42) == 42


def test_breaker_trips_after_threshold_failures():
    breaker, _ = _make_breaker(threshold=2)

    def fail():
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        breaker.call(fail)
    assert breaker.state == "closed"
    with pytest.raises(RuntimeError):
        breaker.call(fail)
    assert breaker.state == "open"

    # Now calls fail fast.
    with pytest.raises(BreakerOpenError):
        breaker.call(fail)


def test_breaker_resets_on_success_before_threshold():
    breaker, _ = _make_breaker(threshold=3)

    def fail():
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        breaker.call(fail)
    breaker.call(lambda: "ok")
    # Next failure shouldn't trip — counter was reset.
    with pytest.raises(RuntimeError):
        breaker.call(fail)
    assert breaker.state == "closed"


def test_breaker_half_opens_after_cooldown_then_closes_on_success():
    breaker, clock = _make_breaker(threshold=1, cooldown=10.0)

    with pytest.raises(RuntimeError):
        breaker.call(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    assert breaker.state == "open"

    clock[0] = 11.0  # past cooldown
    assert breaker.state == "half_open"

    # Probe succeeds → CLOSED.
    breaker.call(lambda: "ok")
    assert breaker.state == "closed"


def test_breaker_half_open_probe_failure_reopens_immediately():
    breaker, clock = _make_breaker(threshold=1, cooldown=10.0)

    with pytest.raises(RuntimeError):
        breaker.call(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    clock[0] = 11.0
    assert breaker.state == "half_open"

    with pytest.raises(RuntimeError):
        breaker.call(lambda: (_ for _ in ()).throw(RuntimeError("still boom")))
    assert breaker.state == "open"


# ---- Per-name registry ----------------------------------------------------


def test_get_breaker_returns_singleton_per_name():
    reset_breakers_for_tests()
    a = get_breaker("amazon")
    b = get_breaker("amazon")
    c = get_breaker("flipkart")
    assert a is b
    assert a is not c


def test_reset_breakers_drops_registry():
    reset_breakers_for_tests()
    a = get_breaker("amazon")
    reset_breakers_for_tests()
    b = get_breaker("amazon")
    assert a is not b
