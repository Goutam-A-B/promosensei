"""Manually run the Amazon scrape + persist cycle.

Usage:
    python -m scripts.run_scraper                # uses settings (live or fixtures)
    SCRAPER_USE_FIXTURES=true python -m scripts.run_scraper

The script is idempotent — re-running upserts the same `(platform, asin)` rows.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

# Allow `python scripts/run_scraper.py` from the backend root.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.scraper import scrape_amazon, upsert_products  # noqa: E402


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )
    log = logging.getLogger("run_scraper")

    Base.metadata.create_all(bind=engine)

    log.info("Scraping Amazon…")
    products = scrape_amazon()
    log.info("Got %d products", len(products))

    if not products:
        log.warning("No products to persist.")
        return 1

    db = SessionLocal()
    try:
        result = upsert_products(db, products, platform="amazon")
    finally:
        db.close()

    log.info(
        "Done. inserted=%d updated=%d skipped=%d errors=%d",
        result.inserted,
        result.updated,
        result.skipped,
        result.errors,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
