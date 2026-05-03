"""(Re)build product embeddings for the active embedding model.

Usage:
    python -m scripts.build_index               # incremental
    python -m scripts.build_index --limit 100   # smoke test on a subset
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.embeddings import reindex_products  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="Only embed the first N products")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s — %(message)s")
    log = logging.getLogger("build_index")

    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        stats = reindex_products(db, limit=args.limit)
    finally:
        db.close()

    log.info(
        "Index build done. model=%s embedded=%d refreshed=%d skipped=%d",
        stats.model_id,
        stats.embedded,
        stats.refreshed,
        stats.skipped,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
