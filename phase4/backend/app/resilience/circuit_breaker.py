"""Three-state circuit breaker.

States:

- CLOSED   — normal. Calls flow through. Consecutive failures count.
- OPEN     — tripped. Calls fail fast with `BreakerOpenError`. After
             `cooldown` seconds we transition to HALF_OPEN.
- HALF_OPEN — one probe call is allowed. Success → CLOSED, failure → OPEN
             with a fresh cooldown.

Per-platform breakers are kept in a module-level registry so
`get_breaker("amazon")` returns the same instance across calls and the
scheduler / metrics endpoint can inspect state without passing it
around.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Callable, TypeVar

from app.observability.metrics import record_circuit_breaker_state

logger = logging.getLogger(__name__)

T = TypeVar("T")

CLOSED = "closed"
OPEN = "open"
HALF_OPEN = "half_open"


class BreakerOpenError(RuntimeError):
    """Raised when a call is rejected because the breaker is OPEN."""


class CircuitBreaker:
    def __init__(
        self,
        name: str,
        *,
        failure_threshold: int = 3,
        cooldown_seconds: float = 600.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._state = CLOSED
        self._failures = 0
        self._opened_at: float | None = None
        record_circuit_breaker_state(name=name, state=self._state)

    @property
    def state(self) -> str:
        with self._lock:
            self._maybe_half_open()
            return self._state

    def call(self, fn: Callable[[], T]) -> T:
        """Wrap `fn`. Raises `BreakerOpenError` if the breaker is OPEN."""
        with self._lock:
            self._maybe_half_open()
            if self._state == OPEN:
                raise BreakerOpenError(f"circuit breaker '{self.name}' is OPEN")
            probe = self._state == HALF_OPEN

        try:
            result = fn()
        except Exception:
            self._record_failure(probe=probe)
            raise
        else:
            self._record_success()
            return result

    # ---- Internal -----------------------------------------------------

    def _maybe_half_open(self) -> None:
        if self._state != OPEN or self._opened_at is None:
            return
        if self._clock() - self._opened_at >= self.cooldown_seconds:
            logger.info("Breaker %s cooled down — moving to HALF_OPEN", self.name)
            self._state = HALF_OPEN
            record_circuit_breaker_state(name=self.name, state=self._state)

    def _record_failure(self, *, probe: bool) -> None:
        with self._lock:
            if probe:
                # Half-open probe failed — reopen immediately.
                self._trip()
                return
            self._failures += 1
            if self._failures >= self.failure_threshold:
                self._trip()

    def _record_success(self) -> None:
        with self._lock:
            if self._state != CLOSED:
                logger.info("Breaker %s reset to CLOSED after success", self.name)
            self._state = CLOSED
            self._failures = 0
            self._opened_at = None
            record_circuit_breaker_state(name=self.name, state=self._state)

    def _trip(self) -> None:
        self._state = OPEN
        self._opened_at = self._clock()
        record_circuit_breaker_state(name=self.name, state=self._state)
        logger.warning(
            "Breaker %s tripped — OPEN for %.0fs", self.name, self.cooldown_seconds,
        )


# ---- Per-name registry ----------------------------------------------------

_breakers: dict[str, CircuitBreaker] = {}
_breakers_lock = threading.Lock()


def get_breaker(
    name: str,
    *,
    failure_threshold: int | None = None,
    cooldown_seconds: float | None = None,
) -> CircuitBreaker:
    """Return the breaker for `name`, creating it on first use.

    Settings come from `app.config` when not overridden. The thresholds
    are remembered after creation — pass overrides only when calling
    from a place that owns the breaker's lifecycle (e.g. tests).
    """
    from app.config import get_settings

    with _breakers_lock:
        existing = _breakers.get(name)
        if existing is not None:
            return existing
        settings = get_settings()
        breaker = CircuitBreaker(
            name,
            failure_threshold=failure_threshold or settings.breaker_failure_threshold,
            cooldown_seconds=cooldown_seconds or settings.breaker_cooldown_seconds,
        )
        _breakers[name] = breaker
        return breaker


def reset_breakers_for_tests() -> None:
    with _breakers_lock:
        _breakers.clear()
