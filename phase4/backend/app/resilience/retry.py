"""Exponential-backoff retry with jitter.

Used to wrap scrape calls, embedding-provider calls, and any other
boundary that talks to a flaky upstream. The signature is deliberately
synchronous because Phase 1–3's scrapers are sync; switch to an async
variant when we move to httpx + asyncio.
"""
from __future__ import annotations

import logging
import random
import time
from typing import Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def retry_with_backoff(
    fn: Callable[[], T],
    *,
    attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    sleep: Callable[[float], None] = time.sleep,
    rng: Callable[[], float] = random.random,
    on_attempt: Callable[[int, Exception], None] | None = None,
) -> T:
    """Call `fn` up to `attempts` times.

    Backoff is `min(max_delay, base_delay * 2**(i-1))` plus full jitter
    on the [0, delay] interval — full jitter avoids the thundering-herd
    problem when many retries fire in lockstep.
    """
    if attempts < 1:
        raise ValueError("attempts must be >= 1")

    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 — caller chooses what to retry on
            last_exc = exc
            if on_attempt is not None:
                on_attempt(attempt, exc)
            if attempt == attempts:
                break
            delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
            jittered = delay * rng()
            logger.warning(
                "Attempt %d/%d failed: %s. Retrying in %.2fs",
                attempt, attempts, exc, jittered,
            )
            sleep(jittered)
    assert last_exc is not None  # pragma: no cover — defensive
    raise last_exc
