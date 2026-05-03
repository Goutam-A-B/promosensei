# PromoSensei — Phase 1

End-to-end Phase 1 slice: an Amazon scraper feeds a Postgres-backed FastAPI service, which a Next.js frontend queries for keyword search.

See [../docs/architecture.md](../docs/architecture.md) for the four-phase plan.

## Layout

```
phase1/
├── backend/        FastAPI + scraper + scheduler
│   ├── app/
│   ├── fixtures/   Local HTML snapshots (used by tests + offline seeding)
│   ├── scripts/    run_scraper.py, seed_db.py
│   └── tests/      pytest suite (in-memory SQLite)
└── frontend/       Next.js 14 (App Router) + Tailwind
```

## Backend

### Setup

```bash
cd phase1/backend
python -m venv .venv && source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
playwright install chromium                          # only if running live scrapes
cp .env.example .env                                 # then edit
```

### Run

```bash
# Seed the DB from local fixtures (no network required)
SCRAPER_USE_FIXTURES=true python scripts/seed_db.py

# Or hit Amazon live
python scripts/run_scraper.py

# Start the API
uvicorn app.main:app --reload
```

The API exposes:

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Liveness probe |
| `GET /health/db` | Confirms DB reachability |
| `GET /search` | Keyword search with filters and sorting |

`/search` query params: `q`, `min_price`, `max_price`, `min_rating`, `platform`, `sort`, `page`, `page_size`.

### Tests

```bash
cd phase1/backend
pytest -q
```

Tests use in-memory SQLite and disable the scheduler — no Postgres or network access required.

## Frontend

### Setup

```bash
cd phase1/frontend
npm install
cp .env.example .env.local
```

### Run

```bash
npm run dev      # http://localhost:3000
```

The page calls `${NEXT_PUBLIC_API_BASE_URL}/search` directly. Make sure the backend is running and reachable.

## What Phase 1 ships (per architecture.md)

- ✅ Amazon scraper with fixture-based offline mode
- ✅ Normalized product schema persisted to a relational store
- ✅ `GET /search` keyword endpoint with filters and sort
- ✅ Next.js search-and-results UI
- ✅ Hourly scrape via APScheduler
- ✅ Unit tests for the normalizer + parser, integration tests for the API

## Edge cases handled in Phase 1

Pulled from [../docs/edge-cases.md](../docs/edge-cases.md):

- 1.8 Sponsored markers → stripped from titles before storage
- 2.1 Missing required fields → row rejected by `normalize`
- 2.2 Inconsistent price formatting (`₹1,999`, `Rs. 1999`, `1999/-`) → handled
- 2.3 Discount math doesn't add up → recompute, never trust label
- 2.4 Original price ≤ current price → null both fields
- 2.5 Implausible discount (>90%) → keep listing, drop discount
- 4.1 Empty query → return all products (trending-style fallback)
- 4.9 Adversarial input → SQLAlchemy parameterized queries everywhere

Phases 2–4 add semantic search, multi-platform aggregation, caching, and observability.
