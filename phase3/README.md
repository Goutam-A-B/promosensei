# PromoSensei — Phase 3

Phase 3 turns the catalog into a unified product graph. Three scrapers (Amazon, Flipkart, Nykaa) feed a matcher that clusters per-platform listings into canonical products. The API surfaces those products grouped, with a per-platform price ladder; a new `/health/scrapers` endpoint surfaces the freshness and success rate of each scraper.

See [../docs/architecture.md](../docs/architecture.md) for the four-phase plan and [../docs/edge-cases.md](../docs/edge-cases.md) for the failure-mode catalog.

## Layout

```
phase3/
├── backend/        FastAPI + 3 scrapers + matcher + embeddings + scheduler
│   ├── app/
│   │   ├── matching/     Brand/model/pack-size extraction + canonical matcher
│   │   ├── embeddings/   Provider abstraction + indexer + similarity helpers
│   │   ├── api/          /health, /health/scrapers, /search
│   │   ├── scraper/      Amazon, Flipkart, Nykaa + persistence (cluster + log)
│   │   ├── query_parser  Lifts numeric/rating constraints out of free text
│   │   ├── ranking       Hybrid scorer (cosine + discount + rating)
│   │   ├── search_service Keyword / semantic / hybrid orchestration
│   │   └── models.py     Product (canonical) + Listing + ScraperRun
│   ├── fixtures/   amazon/, flipkart/, nykaa/ HTML snapshots
│   ├── scripts/    run_scraper.py, seed_db.py, build_index.py
│   └── tests/      pytest suite (in-memory SQLite, no network)
└── frontend/       Next.js 14 with grouped product cards + scraper-health bar
```

## What Phase 3 ships (per architecture.md)

- ✅ Scrapers for **Flipkart** and **Nykaa** (in addition to Amazon)
- ✅ Schema split: `products` (canonical) + `listings` (per-platform)
- ✅ Matcher: brand + model number + pack-size + title fuzz + embedding cosine
- ✅ Hard guards against bad merges: bundle vs single, refurbished vs new, pack-size mismatch, ±25% price sanity
- ✅ Grouped result view: one card per canonical product, listings ranked cheapest-first
- ✅ Per-platform health endpoint (`/health/scrapers`) with 30-day success rate, last-run state, and listing counts
- ✅ Scheduler runs three independent ingest jobs — a single-platform outage doesn't block the others
- ✅ Frontend shows grouped products, per-listing platform pills, and a live scraper-health bar
- ✅ Filters apply at the *listing* level — "earbuds under ₹2000" still finds a product priced lower on Flipkart even if its Amazon listing is over budget

## Backend

### Setup

```bash
cd phase3/backend
python -m venv .venv && .venv\Scripts\activate    # PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium                       # only if running live scrapes
cp .env.example .env                              # then edit (or leave defaults)
```

### Run

```bash
# Seed from fixtures across all 3 platforms and build the embedding index.
SCRAPER_USE_FIXTURES=true python scripts/seed_db.py

# Or scrape live from any subset, then index separately.
python scripts/run_scraper.py amazon flipkart      # subset
python scripts/run_scraper.py                       # all 3
python scripts/build_index.py

# Start the API.
uvicorn app.main:app --reload
```

The API exposes:

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Liveness probe |
| `GET /health/db` | Confirms DB reachability |
| `GET /health/scrapers` | Per-platform success rate, last run, listing counts |
| `GET /search` | Grouped keyword / semantic / hybrid search with filters and sorting |

`/search` query params:

| Param | Notes |
|-------|-------|
| `q` | Free text. Empty returns curated trending deals. |
| `mode` | `keyword` \| `semantic` \| `hybrid`. Default from `SEARCH_DEFAULT_MODE`. |
| `min_price`, `max_price` | Decimal. Override anything the parser extracted from `q`. Applied at the listing level — products with at least one matching listing survive. |
| `min_rating` | 0..5. |
| `platform` | `amazon` \| `flipkart` \| `nykaa`. Limits which listings are surfaced inside each group. |
| `sort` | `relevance` \| `price_asc` \| `price_desc` \| `discount_desc` \| `rating_desc`. Sorts by best (cheapest) listing across the matching set. |
| `page`, `page_size` | Standard pagination. |

### How matching works

[app/matching/](backend/app/matching/) clusters per-platform listings into canonical products. Signals, in priority order:

1. **Hard guards** — bundle vs single, refurbished vs new, pack-size mismatch, ±25% price sanity. These *block* a match outright.
2. **Brand + model number** — exact match on both ⇒ high-confidence merge.
3. **Title fuzz (RapidFuzz token-set)** — handles word reordering and casing.
4. **Embedding cosine** — last line of defense for rephrased titles.

Thresholds err on the side of *not* merging. False splits are recoverable; false merges corrupt canonical product identity.

### Embedding providers

Configure via `EMBEDDING_PROVIDER` in `.env`:

| Value | Use case | Dependencies |
|-------|----------|--------------|
| `hashing` *(default)* | Tests, dev, smoke. Deterministic, in-process, no network. | None |
| `sentence-transformers` | Production-grade local model (`all-MiniLM-L6-v2`). | `pip install sentence-transformers` |
| `openai` | OpenAI `text-embedding-3-small`. | `pip install openai`, `OPENAI_API_KEY` |

Vectors are stored per-`model_id` so two providers never collide. The indexer mixes the canonical title with the brand so two same-titled products from different brands stay apart in the embedding space.

### Tests

```bash
cd phase3/backend
pytest -q
```

In-memory SQLite, scheduler off, hashing embedding provider — no external dependencies.

## Frontend

### Setup

```bash
cd phase3/frontend
npm install
cp .env.example .env.local
```

### Run

```bash
npm run dev      # http://localhost:3000
```

Phase 3 UI additions on top of Phase 2:

- **Grouped product cards** showing the canonical title + brand, the cheapest listing's price, and a `N platforms` chip.
- **Per-platform price ladder** under each card with a row per available listing, each row deep-linking to that platform.
- **Platform filter** in the filter bar.
- **Scraper-health bar** above the search results — green/amber/red pills per platform with tooltips for last run, 30-day success rate, and last error.

## Edge cases handled in Phase 3

Pulled from [../docs/edge-cases.md](../docs/edge-cases.md):

- 3.1 Cross-platform title variance → fuzz + embedding cosine merge
- 3.2 Different products, similar titles → model number weighted heavily
- 3.3 Bundle vs single → blocked by `is_bundle`
- 3.4 Refurbished / renewed → blocked by `is_refurbished`
- 3.5 Pack-size confusion (250ml vs 500ml) → pack-size mismatch blocks merge
- 5.4 Per-platform outage → scheduler isolates platforms; other scrapers + the index keep running
- 5.5 Scraping bug producing nonsense prices → ±25% sanity check blocks the merge

Earlier phases' edge cases (4.x, 5.x, 6.x query/embedding/ranking) carry over unchanged.

Phase 4 adds caching, incremental price refresh, ranking eval harness, and richer observability.
