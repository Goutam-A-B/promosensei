from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import health, metrics, search
from app.config import get_settings
from app.db import Base, engine
from app.observability import setup_logging
from app.scheduler import start_scheduler, stop_scheduler

settings = get_settings()
setup_logging(level=settings.log_level, fmt=settings.log_format)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    scheduler = start_scheduler() if settings.enable_scheduler else None
    try:
        yield
    finally:
        stop_scheduler(scheduler)


app = FastAPI(
    title="PromoSensei API",
    version="0.4.0",
    description=(
        "Phase 4 — three-platform product graph with hybrid search, hot-query "
        "cache, incremental price refresh, retry + per-platform circuit "
        "breakers, structured JSON logs, and a Prometheus /metrics endpoint."
    ),
    lifespan=lifespan,
)

# CORS: explicit origin list for production safety. Vercel preview URLs
# follow the regex pattern below — that lets PR previews talk to the API
# without us hand-maintaining a list, while keeping production locked
# down. Set `api_cors_origins` to your stable Vercel domain.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.api_cors_origins,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(health.router, tags=["health"])
app.include_router(search.router, tags=["search"])
app.include_router(metrics.router, tags=["metrics"])
