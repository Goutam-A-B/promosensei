"""APScheduler wrapper.

Phase 4 layers three things over the Phase 3 scheduler:

1. **Resilience.** Each platform scrape runs through a per-platform
   circuit breaker and a retry-with-backoff. A flaky network blip won't
   blow up a job; a sustained outage won't keep us hammering a dead
   platform.
2. **Incremental refresh.** A separate, lightweight job re-runs the same
   scrape but funnels the result through `refresh_prices` instead of the
   full matcher. Goal: prices reflect platform reality within the
   configured window without paying the matcher cost.
3. **Cache + metrics integration.** Successful ingest invalidates the
   search cache (so users see fresh prices); every job records its
   outcome to /metrics so we can spot a stuck platform from the dashboard.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler

from app.cache import get_cache
from app.config import get_settings
from app.db import SessionLocal
from app.embeddings import reindex_products
from app.models import ScraperRun
from app.observability.metrics import record_scrape_outcome, record_price_refresh
from app.resilience import BreakerOpenError, get_breaker, retry_with_backoff
from app.scraper import (
    refresh_prices,
    scrape_amazon,
    scrape_flipkart,
    scrape_nykaa,
    upsert_listings,
)
from app.schemas import ScrapedListing

logger = logging.getLogger(__name__)


def _resilient_scrape(platform: str, scrape: Callable[[], list[ScrapedListing]]) -> list[ScrapedListing]:
    """Run `scrape` through this platform's breaker + retry policy."""
    settings = get_settings()
    breaker = get_breaker(platform)

    def _retrying() -> list[ScrapedListing]:
        return retry_with_backoff(
            scrape,
            attempts=settings.scraper_retry_attempts,
            base_delay=settings.scraper_retry_base_delay_seconds,
            max_delay=settings.scraper_retry_max_delay_seconds,
        )

    return breaker.call(_retrying)


def _run_platform_ingest(
    platform: str,
    scrape: Callable[[], list[ScrapedListing]],
) -> None:
    """One scrape + persist cycle for a single platform.

    Records a `ScraperRun` row even when the scrape itself crashes — that's
    how /health/scrapers detects platform-level outages instead of just
    silently going stale.
    """
    logger.info("Starting %s ingest job", platform, extra={"platform": platform})
    try:
        listings = _resilient_scrape(platform, scrape)
    except BreakerOpenError as exc:
        logger.warning("%s ingest skipped: %s", platform, exc, extra={"platform": platform})
        _record_failure(platform, str(exc))
        record_scrape_outcome(platform=platform, status="failed")
        return
    except Exception as exc:  # noqa: BLE001
        logger.exception("%s scrape failed", platform, extra={"platform": platform})
        _record_failure(platform, str(exc))
        record_scrape_outcome(platform=platform, status="failed")
        return

    if not listings:
        logger.warning("%s scrape returned 0 listings — recording empty run", platform, extra={"platform": platform})
        _record_failure(platform, "scrape returned 0 listings")
        record_scrape_outcome(platform=platform, status="failed")
        return

    db = SessionLocal()
    try:
        result = upsert_listings(db, listings, platform=platform)
        logger.info(
            "%s ingest finished: inserted=%d updated=%d errors=%d",
            platform, result.inserted, result.updated, result.errors,
            extra={"platform": platform, "inserted": result.inserted, "updated": result.updated, "errors": result.errors},
        )
        if result.errors == 0:
            status = "ok"
        elif result.inserted + result.updated > 0:
            status = "partial"
        else:
            status = "failed"
        record_scrape_outcome(platform=platform, status=status)
        # Successful ingest changes the catalog → invalidate hot search cache.
        if result.inserted + result.updated > 0:
            get_cache().clear()
    finally:
        db.close()


def _run_price_refresh(
    platform: str,
    scrape: Callable[[], list[ScrapedListing]],
) -> None:
    """Lightweight price-only refresh.

    Reuses the same scraper to get the freshest prices but runs them
    through `refresh_prices` rather than `upsert_listings` — no matcher,
    no new product rows, no embedding work.
    """
    settings = get_settings()
    logger.info("Starting %s price-refresh job", platform, extra={"platform": platform, "job": "price_refresh"})
    try:
        listings = _resilient_scrape(platform, scrape)
    except BreakerOpenError as exc:
        logger.warning("%s refresh skipped: %s", platform, exc, extra={"platform": platform})
        return
    except Exception:  # noqa: BLE001
        logger.exception("%s price refresh failed", platform, extra={"platform": platform})
        return

    if not listings:
        return

    db = SessionLocal()
    try:
        result = refresh_prices(
            db,
            listings,
            platform=platform,
            max_age_hours=settings.price_refresh_max_age_hours,
        )
        record_price_refresh(platform=platform, updated=result.updated, errors=result.errors)
        if result.updated > 0:
            get_cache().clear()
    finally:
        db.close()


def _record_failure(platform: str, message: str) -> None:
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        db.add(
            ScraperRun(
                platform=platform,
                started_at=now,
                finished_at=now,
                status="failed",
                error_message=message[:2048] if message else None,
            )
        )
        db.commit()
    except Exception:  # pragma: no cover — defensive only
        logger.exception("Failed to write %s failure marker", platform)
    finally:
        db.close()


def run_amazon_ingest_job() -> None:
    _run_platform_ingest("amazon", scrape_amazon)


def run_flipkart_ingest_job() -> None:
    _run_platform_ingest("flipkart", scrape_flipkart)


def run_nykaa_ingest_job() -> None:
    _run_platform_ingest("nykaa", scrape_nykaa)


def run_amazon_refresh_job() -> None:
    _run_price_refresh("amazon", scrape_amazon)


def run_flipkart_refresh_job() -> None:
    _run_price_refresh("flipkart", scrape_flipkart)


def run_nykaa_refresh_job() -> None:
    _run_price_refresh("nykaa", scrape_nykaa)


def run_index_job() -> None:
    """Incrementally embed new or changed canonical products."""
    logger.info("Starting indexer job")
    db = SessionLocal()
    try:
        stats = reindex_products(db)
        logger.info(
            "Indexer finished: model=%s embedded=%d refreshed=%d skipped=%d",
            stats.model_id, stats.embedded, stats.refreshed, stats.skipped,
        )
    except Exception:
        logger.exception("Indexer job failed")
    finally:
        db.close()


def start_scheduler() -> BackgroundScheduler:
    settings = get_settings()
    scheduler = BackgroundScheduler(daemon=True, timezone="UTC")

    # Heavyweight ingest jobs (full scrape → matcher → persist).
    scheduler.add_job(
        run_amazon_ingest_job,
        trigger="interval",
        hours=max(1, settings.scraper_schedule_hours),
        id="amazon_ingest",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    scheduler.add_job(
        run_flipkart_ingest_job,
        trigger="interval",
        hours=max(1, settings.scraper_flipkart_schedule_hours),
        id="flipkart_ingest",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    scheduler.add_job(
        run_nykaa_ingest_job,
        trigger="interval",
        hours=max(1, settings.scraper_nykaa_schedule_hours),
        id="nykaa_ingest",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )

    # Lightweight price refreshers — high-frequency, cheap.
    refresh_minutes = max(5, settings.price_refresh_minutes)
    for platform, fn in (
        ("amazon", run_amazon_refresh_job),
        ("flipkart", run_flipkart_refresh_job),
        ("nykaa", run_nykaa_refresh_job),
    ):
        scheduler.add_job(
            fn,
            trigger="interval",
            minutes=refresh_minutes,
            id=f"{platform}_price_refresh",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
        )

    scheduler.add_job(
        run_index_job,
        trigger="interval",
        minutes=max(1, settings.indexer_schedule_minutes),
        id="reindex_products",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    scheduler.start()
    logger.info(
        "Scheduler started — full scrape every %dh (amzn) / %dh (flk) / %dh (nyk), "
        "price refresh every %dm, reindex every %dm",
        settings.scraper_schedule_hours,
        settings.scraper_flipkart_schedule_hours,
        settings.scraper_nykaa_schedule_hours,
        refresh_minutes,
        settings.indexer_schedule_minutes,
    )
    return scheduler


def stop_scheduler(scheduler: BackgroundScheduler | None) -> None:
    if scheduler is None:
        return
    try:
        scheduler.shutdown(wait=False)
    except Exception:  # pragma: no cover
        logger.exception("Failed to shut down scheduler cleanly")
