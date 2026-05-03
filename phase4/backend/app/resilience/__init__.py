"""Per-platform retry + circuit-breaker around scraper invocations.

Phase 3 already isolated platforms in the scheduler — a Flipkart crash
didn't stop the Amazon job. Phase 4 adds two more layers:

- `retry_with_backoff` — short-lived transient failures (network blip,
  CDN 503) shouldn't fail the whole scrape. Exponential backoff with a
  cap, capped attempts.
- `CircuitBreaker` — repeated failures shouldn't waste cycles, and
  shouldn't keep DDoSing a platform that's already down. After N
  consecutive failures the breaker trips and rejects calls fast for a
  cooldown window.

Both pieces are pure-Python, fully unit-testable with an injected clock,
and per-platform — there's no global breaker state.
"""
from app.resilience.circuit_breaker import (
    BreakerOpenError,
    CircuitBreaker,
    get_breaker,
    reset_breakers_for_tests,
)
from app.resilience.retry import retry_with_backoff

__all__ = [
    "BreakerOpenError",
    "CircuitBreaker",
    "get_breaker",
    "reset_breakers_for_tests",
    "retry_with_backoff",
]
