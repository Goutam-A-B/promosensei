# syntax=docker/dockerfile:1.6
#
# Backend image for PromoSensei phase 4.
#
# Notes for production:
#   - Playwright/Chromium is intentionally NOT installed. The live deploy
#     runs the scrapers in fixture mode (SCRAPER_USE_FIXTURES=true) so
#     the demo doesn't get IP-banned by Amazon/Flipkart/Nykaa.
#   - The image bundles fixtures/ so the scheduler's price-refresh job
#     has something to feed through `refresh_prices`.
#   - APScheduler ticks in-process; the deploy must be a single instance
#     (Render free / Fly small VM both fit). No external broker needed.

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps: psycopg2 needs libpq, build-essential is dropped after pip install.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install -r requirements.txt \
    && apt-get purge -y --auto-remove build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY app ./app
COPY scripts ./scripts
COPY fixtures ./fixtures
COPY pytest.ini ./pytest.ini

# Render/Fly inject $PORT; default is 8000 for local `docker run`.
ENV PORT=8000
EXPOSE 8000

# Healthcheck so platforms can detect a hung process.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl --fail --silent http://localhost:${PORT}/health || exit 1

# Run uvicorn against the FastAPI app. The PORT envvar is honoured by
# Render and Fly; locally it falls back to 8000.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
