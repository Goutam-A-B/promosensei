# PromoSensei — Project Overview

> One-page reference for the whole project: what it is, how it's built, what runs in production, and what's been delivered.
> For the original four-phase build plan with exit criteria, see [docs/architecture.md](docs/architecture.md).

---

## In one line

A semantic deal search engine across **Amazon · Flipkart · Nykaa** that returns **one card per real product** (not three near-duplicates) with a per-platform price ladder underneath.

## Live demo

| Layer | Service | URL |
|-------|---------|-----|
| Frontend | Vercel hobby | https://promosensei.vercel.app |
| Backend  | Render free  | https://promosensei-api.onrender.com |
| Database | Neon Postgres (free) | (private) |
| CI       | GitHub Actions | https://github.com/Goutam-A-B/promosensei/actions |

Live scrapers are intentionally **off** in production to respect each platform's ToS — the demo runs against a curated 268-product catalogue seeded by [phase4/backend/scripts/seed_demo.py](phase4/backend/scripts/seed_demo.py). The scraper code is real and tested; flipping it on is a single config change.

---

## The problem

Search "noise cancelling headphones" on Google Shopping today and you get the same Sony WH-1000XM5 listed three times — once each from Amazon, Flipkart, Nykaa. PromoSensei deduplicates those into one canonical product card and shows the cheapest platform per item. Naive "join on title" breaks immediately on bundles, refurbs, and size variants — the matcher has explicit hard guards against bad merges.

---

## High-level architecture

```
┌──────────────┐    ┌─────────────┐    ┌─────────────┐
│  Scrapers    │ ─► │  Matcher    │ ─► │  Canonical  │
│  AMZ FLP NYK │    │ brand+model │    │  Product DB │
└──────────────┘    │ +fuzz+cos   │    └──────┬──────┘
                    └─────────────┘           │
                                              ▼
              ┌───────────┐  ┌────────────┐  ┌──────────┐
              │ Web UI    │ ►│  /search   │ ►│  Ranker  │
              │ (Next.js) │ ◄│   cached   │ ◄│ sim+disc │
              └───────────┘  └─────┬──────┘  └──────────┘
                                   │
                            ┌──────┴──────┐
                            │ /metrics    │ Prometheus
                            │ /health/*   │ scrape target
                            └─────────────┘
```

---

## System layers

### 1. Ingest — [phase4/backend/app/scraper/](phase4/backend/app/scraper/)
Per-platform scrapers using Playwright + BeautifulSoup. Each emits a common normalised shape via [normalizer.py](phase4/backend/app/scraper/normalizer.py). Retries and per-platform circuit breakers wrap them so a Flipkart outage doesn't kill Amazon and Nykaa.

- [amazon.py](phase4/backend/app/scraper/amazon.py)
- [flipkart.py](phase4/backend/app/scraper/flipkart.py)
- [nykaa.py](phase4/backend/app/scraper/nykaa.py)
- [persistence.py](phase4/backend/app/scraper/persistence.py)

### 2. Identity / matching — [phase4/backend/app/matching/](phase4/backend/app/matching/)
- [brand.py](phase4/backend/app/matching/brand.py) extracts brand + model from a title.
- [canonicalize.py](phase4/backend/app/matching/canonicalize.py) decides whether a new listing collapses into an existing canonical product.

**Hard merge guards** run *before* any fuzzy/embedding score is computed:
- size/volume mismatch (250 ml ≠ 500 ml)
- refurbished flag mismatch
- bundle flag mismatch
- ±25 % price sanity

False-merges corrupt canonical product identity (one wrong row poisons every future search) — false-splits are recoverable by user feedback. The matcher errs on the side of splitting.

### 3. Storage — [phase4/backend/app/models.py](phase4/backend/app/models.py)
PostgreSQL on Neon with two key tables:

- `products` — canonical row per real-world product.
- `listings` — one row per `(product, platform)` pair (URL, price, original price, discount, rating, last seen).

Embeddings are stored as a JSON-vector index in process today; pgvector swap is documented in [docs/architecture.md](docs/architecture.md).

### 4. Search service — [phase4/backend/app/search_service.py](phase4/backend/app/search_service.py)
- [query_parser.py](phase4/backend/app/query_parser.py) extracts numeric filters from natural language ("under 2000" → `max_price=2000`, "4 stars" → `min_rating=4`).
- Three search modes:
  - **Keyword** — Postgres full-text search (`tsvector` / `ts_rank`).
  - **Semantic** — cosine similarity on embeddings via [embeddings/similarity.py](phase4/backend/app/embeddings/similarity.py).
  - **Hybrid** — Reciprocal Rank Fusion of the two.
- **Listing-level filtering, product-level grouping** — "earbuds under ₹2 000" still surfaces a product whose Amazon listing is overpriced if its Flipkart listing fits. The naive approach drops the whole product.
- [ranking.py](phase4/backend/app/ranking.py) blends similarity + discount + rating into the final ordering.

### 5. Embeddings — [phase4/backend/app/embeddings/](phase4/backend/app/embeddings/)
Pluggable provider via [factory.py](phase4/backend/app/embeddings/factory.py):

- [hashing.py](phase4/backend/app/embeddings/hashing.py) — deterministic, dependency-free fallback.
- [sentence_transformer_provider.py](phase4/backend/app/embeddings/sentence_transformer_provider.py) — local model.
- [openai_provider.py](phase4/backend/app/embeddings/openai_provider.py) — managed API.

[indexer.py](phase4/backend/app/embeddings/indexer.py) builds and updates the in-process index.

### 6. Cache — [phase4/backend/app/cache/](phase4/backend/app/cache/)
Hot-query LRU cache fronting `/search`. Pluggable backend ([factory.py](phase4/backend/app/cache/factory.py)):

- [memory.py](phase4/backend/app/cache/memory.py) — in-process LRU (current).
- [redis_provider.py](phase4/backend/app/cache/redis_provider.py) — Redis adapter (ready, not deployed).

The frontend's latency badge surfaces `cache hit · 12 ms` vs `fresh · 87 ms` so the cache is observable live.

### 7. API — [phase4/backend/app/api/](phase4/backend/app/api/)
FastAPI routers:

- [search.py](phase4/backend/app/api/search.py) — `GET /search?q=…&mode=…&min_price=…`
- [health.py](phase4/backend/app/api/health.py) — `/health` + `/health/scrapers` (per-platform success rate, last run, listings count).
- [metrics.py](phase4/backend/app/api/metrics.py) — `/metrics` in Prometheus text-exposition format.

Pydantic v2 schemas in [schemas.py](phase4/backend/app/schemas.py).

### 8. Resilience — [phase4/backend/app/resilience/](phase4/backend/app/resilience/)
- [circuit_breaker.py](phase4/backend/app/resilience/circuit_breaker.py) — three-state `CLOSED → OPEN → HALF_OPEN` breaker with an injectable clock (so it's fully unit-testable without `time.sleep`).
- [retry.py](phase4/backend/app/resilience/retry.py) — exponential backoff with jitter.

### 9. Observability — [phase4/backend/app/observability/](phase4/backend/app/observability/)
- [logging.py](phase4/backend/app/observability/logging.py) — line-delimited JSON logs (works with any log shipper, no vendor lock-in).
- [metrics.py](phase4/backend/app/observability/metrics.py) — hand-rolled counters / gauges / histograms registry (avoids pulling in `prometheus_client` for a handful of values).

### 10. Quality gate — [phase4/backend/app/eval/](phase4/backend/app/eval/)
- [queries.yaml](phase4/backend/app/eval/queries.yaml) — 15 hand-labelled queries with expected results.
- [harness.py](phase4/backend/app/eval/harness.py) — runs each query and computes **NDCG@5** + **Precision@3**.
- [metrics.py](phase4/backend/app/eval/metrics.py) — hand-rolled metric implementations.
- CI test [test_eval_regression.py](phase4/backend/tests/test_eval_regression.py) **blocks the merge** if either metric drops below the threshold in [config.py](phase4/backend/app/config.py) (`EVAL_MIN_NDCG_AT_5`, `EVAL_MIN_PRECISION_AT_3`).

### 11. Scheduler — [phase4/backend/app/scheduler.py](phase4/backend/app/scheduler.py)
APScheduler drives **incremental price refresh** — it walks the listings table by staleness rather than re-scraping everything, which keeps the free tier inside its CPU budget.

---

## Frontend — [phase4/frontend/app/page.tsx](phase4/frontend/app/page.tsx)

Single self-contained Next.js 14 page (App Router). Material Design 3 "Expressive" dark theme. **Everything inlined into one file** so the UI can be replaced or rolled back atomically.

### Layout
- **Sticky top app bar** with translucent dark glass + gradient logo tile.
- **Sticky mini search bar** that slides in once you scroll past the hero.
- **Animated mesh-gradient hero** with a `Live · India · 3 platforms` pulse badge, a calm indigo→sky→amber gradient headline, and a pill-shaped search field.
- **Inline category chips** + example-query chips.
- **Mode toggle + Compare button + filters bar + platform chips** in two compact rows.
- **Scraper-health strip** showing per-platform success rate.
- **Featured "🔥 Trending" card** — compact left-rail image (180 px) + meta column with brand, title, price, savings vs other platforms, and per-platform rows that link out.
- **Product grid** — 4 cols on xl, glass cards with brand-tinted hover halos.
- **Big-deal pulse** — items with ≥40 % off get an emerald ring + pulsing badge.
- **Heart save** toggle (cosmetic, local state).
- **Scroll-to-top FAB** below the fold.

### Compare panel
Click **⚡ Compare all 3** next to the mode toggle and the panel fires three parallel `/search` calls (page_size=6 each) and renders the results in three side-by-side columns:

| Column | Mode | Tint |
|---|---|---|
| **Keyword**  | Postgres FTS · literal word match | amber |
| **Hybrid**   | Keyword + vector fusion | indigo |
| **Semantic** | Pure embedding similarity | emerald |

Results that appear in **only one** mode get an emerald ring and an "unique" badge — that's where keyword/hybrid/semantic visibly diverge. Each column header shows count, latency, and cache-hit status.

The panel is the recruiter-friendly *proof* the modes do different things on a small catalogue. Verified examples on the live API:

| Query | Keyword | Hybrid | Semantic |
|---|---|---|---|
| `wireless earbuds`  | 3 | 12 | 12 |
| `earbuds for gym`   | **0** | 3 | 3 |

For `earbuds for gym`, keyword returns zero because "gym" doesn't appear in any title — but vector search infers the intent and pulls in wireless earbuds. That's the headline win for embeddings.

### Theme

| Token | Value |
|---|---|
| Background | `#161A22` (neutral cool slate, no purple cast) |
| Form chrome | `#1B1F28` |
| Primary accent | `indigo-500` / `indigo-400` |
| Secondary accent | `sky-500` |
| Discount / savings | `emerald-400/500` |
| Save (heart) | `rose-500` |
| Text primary | `slate-100` / `white` |
| Text muted | `slate-400` / `slate-500` |

All glow shadows reference indigo rgba `(99,102,241,…)` — softer than the original violet `(168,85,247,…)` to avoid eye strain.

---

## The four phases (the portfolio narrative)

Each phase is a self-contained directory. Reading them in order shows the engineering progression.

| Phase | Theme | Key delivery |
|-------|-------|---|
| [phase1/](phase1/) | **Foundation** | Single Amazon scraper · keyword search · minimal Next.js UI |
| [phase2/](phase2/) | **Semantic intelligence** | Embedding pipeline · pluggable provider · hybrid ranking |
| [phase3/](phase3/) | **Cross-platform aggregation** | Flipkart + Nykaa scrapers · canonical matcher · grouped results · `/health/scrapers` |
| [phase4/](phase4/) | **Real-time, scale & polish** | Hot-query cache · incremental price refresh · circuit breakers · JSON logs · `/metrics` · NDCG eval gate |

The live demo runs **phase 4**.

---

## Stack

**Backend** · FastAPI · SQLAlchemy 2.0 · Pydantic v2 · APScheduler · RapidFuzz · BeautifulSoup · Playwright · pytest (**181 passing**)

**Frontend** · Next.js 14 (App Router) · React 18 · TypeScript · Tailwind CSS

**Data** · PostgreSQL (Neon) · in-process JSON-vector index (pgvector swap documented)

**Ops** · Docker · GitHub Actions CI · Prometheus text exposition · structured JSON logs

---

## Run it locally

```powershell
# Backend
cd phase4/backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python scripts/seed_demo.py --reset      # seed ~268 curated products
uvicorn app.main:app --reload            # http://localhost:8000

# Frontend (separate terminal)
cd phase4/frontend
npm install
# .env.local already points at http://localhost:8000
npm run dev                              # http://localhost:3000
```

```powershell
# Eval harness
cd phase4/backend
python scripts/run_eval.py               # NDCG@5, Precision@3, hit rate, coverage

# Test suite
pytest -q                                # 181 passing
```

> **CORS note:** the production API only allows `https://promosensei.vercel.app` as an origin, so local-frontend → prod-API is blocked by the browser. Local dev needs a local backend, or temporarily add `http://localhost:3000` to `API_CORS_ORIGINS` on Render.

---

## What recruiters can poke at on the live demo

1. **Compare all 3** — proves the search modes do different things (keyword can return 0 where semantic returns 12).
2. **Latency badge** — `cache hit · 12 ms` vs `fresh · 87 ms` shows the Phase 4 cache visible in real time.
3. **Scraper-health chips** — Amazon / Flipkart / Nykaa with 30-day success rate %, demonstrating `/health/scrapers` is wired through.
4. **/metrics on the API host** — a real Prometheus scrape target.
5. **Per-platform rows on each card** — click any platform to open its product/search page; the cheapest is tagged `BEST`.
6. **Filters** — sort, min/max price, min rating, platform chip toggle, "clear all".

---

## Recent changes (delta worth knowing)

- Frontend home was a multi-component light UI ([phase4/frontend/components/](phase4/frontend/components/)). It has been **fully replaced** with a single self-contained Material 3 dark page at [phase4/frontend/app/page.tsx](phase4/frontend/app/page.tsx). The old `components/` directory was deleted in commit `c03b535`.
- Featured card was hero-sized; now a compact "🔥 Trending" banner with a 180 px image rail and no panning gradient ring (commit `bf14dd7`).
- Redundant "Open on {platform}" CTA buttons removed from product cards — the per-platform rows are the link (commit `bf14dd7`).
- "Compare all 3" mode-comparison panel added next to the mode toggle (commit `ab55b72`).

---

## Documentation map

- [README.md](README.md) — public-facing project pitch with the architecture diagram and quick-start.
- [OVERVIEW.md](OVERVIEW.md) — *this file.* One-page reference for everything that's been built.
- [DEPLOY.md](DEPLOY.md) — click-by-click free-tier deploy guide (Vercel + Render + Neon).
- [docs/architecture.md](docs/architecture.md) — the full four-phase build plan with per-phase exit criteria.
- [docs/edge-cases.md](docs/edge-cases.md) — the failure-mode catalogue every phase tests against.
- [docs/problemstatement.md](docs/problemstatement.md) — the original problem framing.
- Per-phase READMEs in [phase1/](phase1/README.md) · [phase2/](phase2/README.md) · [phase3/](phase3/README.md) · [phase4/](phase4/README.md).
