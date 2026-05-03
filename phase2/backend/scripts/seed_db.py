"""Seed the database from local fixtures and build the embedding index.

Running this once after a fresh checkout gives the API enough catalog +
vectors to serve semantic queries end-to-end with no network access.
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
from app.scraper import AmazonScraper, upsert_products  # noqa: E402


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s — %(message)s")
    log = logging.getLogger("seed")

    Base.metadata.create_all(bind=engine)
    products = AmazonScraper(use_fixtures=True).scrape()
    log.info("Parsed %d products from fixtures", len(products))

    if not products:
        log.error("No fixtures found. Add HTML to fixtures/amazon/.")
        return 1

    db = SessionLocal()
    try:
        result = upsert_products(db, products, platform="amazon")
        log.info(
            "Upsert: inserted=%d updated=%d errors=%d",
            result.inserted,
            result.updated,
            result.errors,
        )
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
