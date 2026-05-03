from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import health, search
from app.config import get_settings
from app.db import Base, engine
from app.scheduler import start_scheduler, stop_scheduler

settings = get_settings()


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
    version="0.3.0",
    description=(
        "Phase 3 — Amazon, Flipkart, and Nykaa ingestion clustered into a "
        "canonical product graph, with semantic / keyword / hybrid search "
        "and per-platform health monitoring."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.api_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, tags=["health"])
app.include_router(search.router, tags=["search"])
