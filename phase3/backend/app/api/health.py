"""Health endpoints.

`/health` and `/health/db` are liveness probes. `/health/scrapers` exposes
per-platform freshness and success rate — the operability signal called out
in Phase 3 of architecture.md.
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import Listing, ScraperRun
from app.schemas import ScraperHealth, ScrapersHealthResponse

router = APIRouter()


# Platforms we track even if they've never run yet — surfacing them as "no
# data" lets the frontend visualise outages rather than silently hiding them.
_TRACKED_PLATFORMS = ("amazon", "flipkart", "nykaa")


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/db")
def health_db(db: Session = Depends(get_db)) -> dict[str, str]:
    db.execute(text("SELECT 1"))
    return {"status": "ok", "db": "reachable"}


@router.get("/health/scrapers", response_model=ScrapersHealthResponse)
def health_scrapers(db: Session = Depends(get_db)) -> ScrapersHealthResponse:
    settings = get_settings()
    window_start = datetime.now(timezone.utc) - timedelta(days=settings.health_window_days)

    # Aggregate run stats per platform within the window. `ok` counts as success;
    # `partial` and `failed` both count against the success rate so the metric
    # genuinely reflects how often a scrape produced clean data.
    success_expr = case((ScraperRun.status == "ok", 1), else_=0)
    rows = db.execute(
        select(
            ScraperRun.platform,
            func.count(ScraperRun.id).label("runs"),
            func.sum(success_expr).label("successes"),
            func.max(ScraperRun.started_at).label("last_started"),
        )
        .where(ScraperRun.started_at >= window_start)
        .group_by(ScraperRun.platform)
    ).all()
    by_platform = {row.platform: row for row in rows}

    listing_counts = dict(
        db.execute(
            select(Listing.platform, func.count(Listing.id)).group_by(Listing.platform)
        ).all()
    )

    healths: list[ScraperHealth] = []
    for platform in _TRACKED_PLATFORMS:
        row = by_platform.get(platform)
        runs = int(row.runs) if row else 0
        successes = int(row.successes or 0) if row else 0
        success_rate = (successes / runs) if runs else 0.0

        latest = _latest_run(db, platform)
        healths.append(
            ScraperHealth(
                platform=platform,
                last_started_at=latest.started_at if latest else None,
                last_finished_at=latest.finished_at if latest else None,
                last_status=latest.status if latest else None,
                success_rate_30d=round(success_rate, 3),
                runs_30d=runs,
                listings_count=int(listing_counts.get(platform, 0)),
                last_error=latest.error_message if latest else None,
            )
        )

    return ScrapersHealthResponse(scrapers=healths)


def _latest_run(db: Session, platform: str) -> ScraperRun | None:
    return db.scalars(
        select(ScraperRun)
        .where(ScraperRun.platform == platform)
        .order_by(ScraperRun.started_at.desc())
        .limit(1)
    ).first()
