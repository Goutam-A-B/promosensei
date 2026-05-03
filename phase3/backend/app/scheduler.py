"""APScheduler wrapper.

Phase 1 ran a single Amazon scrape job. Phase 2 added the indexer. Phase 3
adds Flipkart and Nykaa: each platform runs on its own interval and stages
its results into the same canonical product graph through `upsert_listings`.

The jobs are independent — if Flipkart fails, Nykaa and Amazon still run,
and the indexer still embeds whatever's already in the DB (edge case 5.4 —
a single-platform outage must never block the rest of the system).
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler

from app.config import get_settings
from app.db import SessionLocal
from app.embeddings import reindex_products
from app.models import ScraperRun
from app.scraper import (
    scrape_amazon,
    scrape_flipkart,
    scrape_nykaa,
    upsert_listings,
)
from app.schemas import ScrapedListing

logger = logging.getLogger(__name__)


def _run_platform_ingest(
    platform: str,
    scrape: Callable[[], list[ScrapedListing]],
) -> None:
    """One scrape + persist cycle for a single platform.

    Records a `ScraperRun` row even when the scrape itself crashes — that's
    how /health/scrapers detects platform-level outages instead of just
    silently going stale (architecture.md "Per-platform health monitoring").
    """
    logger.info("Starting %s ingest job", platform)
    try:
        listings = scrape()
    except Exception as exc:  # noqa: BLE001 — record outage, don't crash scheduler
        logger.exception("%s scrape failed", platform)
        _record_failure(platform, str(exc))
        return

    if not listings:
        logger.warning("%s scrape returned 0 listings — recording empty run", platform)
        _record_failure(platform, "scrape returned 0 listings")
        return

    db = SessionLocal()
    try:
        result = upsert_listings(db, listings, platform=platform)
        logger.info(
            "%s ingest finished: inserted=%d updated=%d errors=%d",
            platform,
            result.inserted,
            result.updated,
            result.errors,
        )
    finally:
        db.close()


def _record_failure(platform: str, message: str) -> None:
    """Write a `failed` ScraperRun so the health endpoint reflects the outage."""
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


def run_index_job() -> None:
    """Incrementally embed new or changed canonical products."""
    logger.info("Starting indexer job")
    db = SessionLocal()
    try:
        stats = reindex_products(db)
        logger.info(
            "Indexer finished: model=%s embedded=%d refreshed=%d skipped=%d",
            stats.model_id,
            stats.embedded,
            stats.refreshed,
            stats.skipped,
        )
    except Exception:
        logger.exception("Indexer job failed")
    finally:
        db.close()


def start_scheduler() -> BackgroundScheduler:
    settings = get_settings()
    scheduler = BackgroundScheduler(daemon=True, timezone="UTC")
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
        "Scheduler started — amazon every %dh, flipkart every %dh, nykaa every %dh, reindex every %dm",
        settings.scraper_schedule_hours,
        settings.scraper_flipkart_schedule_hours,
        settings.scraper_nykaa_schedule_hours,
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
