# PromoSensei — Phase 2

Phase 2 layers semantic intelligence on top of the Phase 1 pipeline. Every product gets an embedding vector; queries are pre-parsed for natural-language constraints, embedded, and re-ranked with a hybrid scorer.

See [../docs/architecture.md](../docs/architecture.md) for the four-phase plan and [../docs/edge-cases.md](../docs/edge-cases.md) for the failure-mode catalog.

## Layout

```
phase2/
├── backend/        FastAPI + scraper + embeddings + scheduler
│   ├── app/
│   │   ├── embeddings/   Provider abstraction + indexer + similarity helpers
│   │   ├── api/          /health, /search
│   │   ├── scraper/      Phase 1 Amazon scraper (unchanged)
│   │   ├── query_parser  Lifts numeric/rating constraints out of free text
│   │   ├── ranking       Hybrid scorer (cosine + discount + rating)
│   │   └── search_service Keyword / semantic / hybrid orchestration
│   ├── fixtures/   Local HTML snapshots (used by tests + offline seeding)
│   ├── scripts/    run_scraper.py, seed_db.py, build_index.py
│   └── tests/      pytest suite (in-memory SQLite, no network)
└── frontend/       Next.js 14 (App Router) + Tailwind + mode toggle
```

## What Phase 2 ships (per architecture.md)

- ✅ Embedding generation for every product (pluggable provider)
- ✅ Vector storage in `product_embeddings` table, keyed by `model_id`
- ✅ Query embedding pipeline at request time
- ✅ Natural-language query parser (`under 2000`, `4-star`, `between 5k and 10k`)
- ✅ Hybrid ranker: similarity + winsorized discount + Bayesian-smoothed rating
- ✅ Three-mode search API (`keyword`, `semantic`, `hybrid`)
- ✅ Cold-start fallback to keyword search when the index is empty
- ✅ Incremental re-embed on title changes (`title_hash`)
- ✅ Frontend mode toggle, parsed-intent badge, per-result similarity score
- ✅ APScheduler runs both the scraper and the indexer

## Backend

### Setup

```bash
cd phase2/backend
python -m venv .venv && .venv\Scripts\activate    # PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium                       # only if running live scrapes
cp .env.example .env                              # then edit
```

### Run

```bash
# Seed from fixtures and build the embedding index in one shot.
SCRAPER_USE_FIXTURES=true python scripts/seed_db.py

# Or scrape live from Amazon, then index separately.
python scripts/run_scraper.py
python scripts/build_index.py

# Start the API.
uvicorn app.main:app --reload
```

The API exposes:

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Liveness probe |
| `GET /health/db` | Confirms DB reachability |
| `GET /search` | Keyword / semantic / hybrid search with filters and sorting |

`/search` query params:

| Param | Notes |
|-------|-------|
| `q` | Free text. Empty returns curated trending deals. |
| `mode` | `keyword` \| `semantic` \| `hybrid`. Default from `SEARCH_DEFAULT_MODE`. |
| `min_price`, `max_price` | Decimal. Override anything the parser extracted from `q`. |
| `min_rating` | 0..5. |
| `platform` | Single platform filter (only `amazon` in Phase 2). |
| `sort` | `relevance` \| `price_asc` \| `price_desc` \| `discount_desc` \| `rating_desc`. |
| `page`, `page_size` | Standard pagination. |

### Embedding providers

Configure via `EMBEDDING_PROVIDER` in `.env`:

| Value | Use case | Dependencies |
|-------|----------|--------------|
| `hashing` *(default)* | Tests, dev, smoke. Deterministic, in-process, no network. | None |
| `sentence-transformers` | Production-grade local model (`all-MiniLM-L6-v2`). | `pip install sentence-transformers` |
| `openai` | OpenAI `text-embedding-3-small`. | `pip install openai`, `OPENAI_API_KEY` |

Vectors are stored per-`model_id` so two providers never collide. Switching providers triggers a re-index on the next scheduler tick (edge case 5.2 in [edge-cases.md](../docs/edge-cases.md)).

### Tests

```bash
cd phase2/backend
pytest -q
```

In-memory SQLite, scheduler off, the hashing embedding provider — no external dependencies.

## Frontend

### Setup

```bash
cd phase2/frontend
npm install
cp .env.example .env.local
```

### Run

```bash
npm run dev      # http://localhost:3000
```

The page calls `${NEXT_PUBLIC_API_BASE_URL}/search`. The Phase 2 UI adds:

- A **mode toggle** (Semantic / Hybrid / Keyword).
- A **parsed-intent badge** showing what the query parser pulled out (`max_price=2000`).
- A **fallback chip** when the requested mode degraded (e.g. semantic → keyword on cold start).
- **Per-result similarity** percentage on each card in semantic / hybrid mode.

## Edge cases handled in Phase 2

Pulled from [../docs/edge-cases.md](../docs/edge-cases.md):

- 4.1 Empty query → curated trending deals; never embed an empty string
- 4.5 Numeric constraints in NL → parser lifts them into structured filters
- 4.9 Adversarial input → still parameterized everywhere
- 5.1 Cold start with empty index → fall back to keyword search with a banner
- 5.2 Embedding model upgrade → vectors keyed by `model_id`, dual-write safe
- 5.3 Stale embedding after product update → re-embed on `title_hash` change
- 5.4 Vector store outage → keyword path is always available
- 6.1 Tied scores → deterministic tiebreak by `product_id`
- 6.2 New products with no rating → Bayesian smoothing toward the prior
- 6.3 Outlier discounts → winsorized at 95th percentile before normalization

Phases 3–4 add multi-platform aggregation, caching, ranking eval harness, and observability.
