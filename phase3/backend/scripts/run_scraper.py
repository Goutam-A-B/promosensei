"""Manually run scrape + persist for one or all platforms.

Usage:
    python scripts/run_scraper.py                    # all 3 platforms
    python scripts/run_scraper.py amazon             # one platform
    python scripts/run_scraper.py flipkart nykaa     # subset
    SCRAPER_USE_FIXTURES=true python scripts/run_scraper.py

The script is idempotent — re-running upserts the same `(platform, id)` rows.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.scraper import (  # noqa: E402
    scrape_amazon,
    scrape_flipkart,
    scrape_nykaa,
    upsert_listings,
)
from app.schemas import ScrapedListing  # noqa: E402


SCRAPERS: dict[str, Callable[[], list[ScrapedListing]]] = {
    "amazon": scrape_amazon,
    "flipkart": scrape_flipkart,
    "nykaa": scrape_nykaa,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "platforms",
        nargs="*",
        choices=sorted(SCRAPERS) + [],
        help="Subset of platforms to scrape (default: all).",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )
    log = logging.getLogger("run_scraper")

    Base.metadata.create_all(bind=engine)

    targets = args.platforms or list(SCRAPERS.keys())
    db = SessionLocal()
    overall_failed = True
    try:
        for platform in targets:
            log.info("Scraping %s…", platform)
            try:
                listings = SCRAPERS[platform]()
            except Exception:
                log.exception("[%s] scrape crashed", platform)
                continue
            log.info("[%s] got %d listings", platform, len(listings))
            if not listings:
                continue
            result = upsert_listings(db, listings, platform=platform)
            log.info(
                "[%s] inserted=%d updated=%d skipped=%d errors=%d",
                platform,
                result.inserted,
                result.updated,
                result.skipped,
                result.errors,
            )
            if result.inserted + result.updated > 0:
                overall_failed = False
    finally:
        db.close()

    return 1 if overall_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
