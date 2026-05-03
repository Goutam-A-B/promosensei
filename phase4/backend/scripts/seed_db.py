"""Seed the database from local fixtures across all 3 platforms, then build
the embedding index.

Running this once after a fresh checkout gives the API enough catalog +
vectors to serve grouped search end-to-end with no network access.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.embeddings import reindex_products  # noqa: E402
from app.scraper import (  # noqa: E402
    AmazonScraper,
    FlipkartScraper,
    NykaaScraper,
    upsert_listings,
)


PLATFORMS = (
    ("amazon", AmazonScraper),
    ("flipkart", FlipkartScraper),
    ("nykaa", NykaaScraper),
)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s — %(message)s")
    log = logging.getLogger("seed")

    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        # Order matters: Amazon first establishes the canonical pool. Flipkart
        # and Nykaa then *match into* it instead of spawning duplicate
        # canonicals — the order minimises false-split rates while the matcher
        # warms up.
        total_inserted = total_updated = 0
        for platform, ScraperCls in PLATFORMS:
            listings = ScraperCls(use_fixtures=True).scrape()
            log.info("[%s] parsed %d listings from fixtures", platform, len(listings))
            if not listings:
                log.warning("[%s] no fixture listings — skipping upsert", platform)
                continue
            result = upsert_listings(db, listings, platform=platform)
            log.info(
                "[%s] upsert: inserted=%d updated=%d errors=%d",
                platform,
                result.inserted,
                result.updated,
                result.errors,
            )
            total_inserted += result.inserted
            total_updated += result.updated

        if total_inserted + total_updated == 0:
            log.error("No listings ingested. Check fixtures/{amazon,flipkart,nykaa}/.")
            return 1

        stats = reindex_products(db)
        log.info(
            "Index: model=%s embedded=%d refreshed=%d skipped=%d",
            stats.model_id,
            stats.embedded,
            stats.refreshed,
            stats.skipped,
        )
    finally:
        db.close()

    log.info("Seed complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
