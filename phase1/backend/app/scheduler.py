"""APScheduler wrapper that runs the Amazon scraper on a recurring interval."""
from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app.config import get_settings
from app.db import SessionLocal
from app.scraper import scrape_amazon, upsert_products

logger = logging.getLogger(__name__)


def run_amazon_ingest_job() -> None:
    """One scrape + persist cycle. Designed to be safe to call from a scheduler."""
    logger.info("Starting Amazon ingest job")
    try:
        products = scrape_amazon()
    except Exception:
        logger.exception("Amazon scrape failed")
        return

    if not products:
        logger.warning("Amazon scrape returned 0 products — skipping upsert")
        return

    db = SessionLocal()
    try:
        result = upsert_products(db, products, platform="amazon")
        logger.info(
            "Amazon ingest finished: inserted=%d updated=%d errors=%d",
            result.inserted,
            result.updated,
            result.errors,
        )
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
    scheduler.start()
    logger.info(
        "Scheduler started — Amazon ingest every %d hour(s)", settings.scraper_schedule_hours
    )
    return scheduler


def stop_scheduler(scheduler: BackgroundScheduler | None) -> None:
    if scheduler is None:
        return
    try:
        scheduler.shutdown(wait=False)
    except Exception:  # pragma: no cover
        logger.exception("Failed to shut down scheduler cleanly")
