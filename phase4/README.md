# PromoSensei — Phase 4

Phase 4 turns the Phase 3 product graph into a system that feels **fast, fresh, and trustworthy** in production. Same three scrapers, same canonical-product graph, same hybrid search — now with a hot-query cache, an incremental price refresher, retry + per-platform circuit breakers, structured JSON logs, a Prometheus `/metrics` endpoint, and a ranking-quality regression suite.

See [../docs/architecture.md](../docs/architecture.md) for the four-phase plan and [../docs/edge-cases.md](../docs/edge-cases.md) for the failure-mode catalog.

## Layout

```
phase4/
├── backend/        FastAPI + caching + observability + eval harness
│   ├── app/
│   │   ├── cache/          Pluggable cache (memory default, Redis-ready)
│   │   ├── observability/  JSON logging + Prometheus-format metrics
│   │   ├── resilience/     Retry-with-backoff + per-platform circuit breaker
│   │   ├── eval/           NDCG / Precision@k harness + queries.yaml
│   │   ├── api/            /health, /search (cached), /metrics
│   │   ├── scraper/        + refresh_prices (incremental refresh)
│   │   ├── matching/       (carried from Phase 3)
│   │   ├── embeddings/     (carried from Phase 3)
│   │   └── scheduler.py    Full ingest + price refresh + reindex jobs
│   ├── scripts/    run_eval.py + Phase 3 scripts
│   └── tests/      pytest suite (181 tests, in-memory SQLite, no network)
└── frontend/       Next.js 14 — adds latency / cache-hit badge to Phase 3 UI
```

## What Phase 4 ships (per architecture.md)

- ✅ **Caching layer** for hot queries — pluggable `memory` (default, in-process LRU+TTL) or `redis`. Cache key includes filters, mode, sort, and pagination.
- ✅ **Incremental price refresh** — separate scheduler job that updates price/discount/rating/last-seen on known listings without rerunning the matcher.
- ✅ **Resilience** — exponential-backoff retry + three-state circuit breaker per platform. A flaky network blip retries; a sustained outage trips the breaker so we stop hammering a dead platform.
- ✅ **Ranking eval harness** — 15 hand-labeled queries with NDCG@5 / Precision@3 / hit-rate / coverage. Backed by a CI regression test that fails when either headline metric drops below the configured floor.
- ✅ **Observability** — structured JSON logs (one line, all context, ready for Loki/Cloudwatch) and a Prometheus-format `/metrics` endpoint covering search latency, cache hits/misses, scrape outcomes, price refreshes, and breaker state.

### Architecture deltas from Phase 3

```
Request                            ┌─────────── /metrics  (Prometheus scrape)
   │                               │
   ▼                               │
┌──────────────┐                   │
│   /search    │──► cache.get ──► hit ──► return (cache_hit=true)
│  (FastAPI)   │        │
└──────────────┘        ▼ miss
                    run_search ──► cache.set ──► return (cache_hit=false, latency_ms)

Scheduler
├── full ingest      (per-platform, every 6–12 h)        wrapped in breaker + retry
├── price refresh    (per-platform, every 30 min)        wrapped in breaker + retry
└── reindex          (every 30 min)
```

## Backend

### Setup

```bash
cd phase4/backend
python -m venv .venv && .venv\Scripts\activate    # PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium                       # only for live scrapes
cp .env.example .env                              # then edit (or leave defaults)
```

### Run

```bash
# Seed from fixtures across all 3 platforms and build the embedding index.
SCRAPER_USE_FIXTURES=true python scripts/seed_db.py

# Or scrape live, then index.
python scripts/run_scraper.py amazon flipkart      # subset
python scripts/build_index.py

# Start the API.
uvicorn app.main:app --reload
```

### Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Liveness probe |
| `GET /health/db` | Confirms DB reachability |
| `GET /health/scrapers` | Per-platform success rate, last run, listing counts |
| `GET /search` | Cached, instrumented keyword/semantic/hybrid search |
| `GET /metrics` | Prometheus text-format scrape target |

`/search` returns the Phase 3 grouped shape **plus**:

- `cache_hit: bool` — did this request hit the cache?
- `latency_ms: float` — server-measured end-to-end latency.

### Cache

| Setting | Default | Notes |
|---------|---------|-------|
| `CACHE_PROVIDER` | `memory` | `memory` (LRU+TTL, in-process) · `redis` · `none` |
| `CACHE_TTL_SECONDS` | `300` | Architecture.md target — 5 minutes |
| `CACHE_MAX_ENTRIES` | `1024` | LRU cap for the memory backend |
| `CACHE_REDIS_URL` | `redis://localhost:6379/0` | Used only when `CACHE_PROVIDER=redis` |

The cache key hashes: query, mode, all filters, sort, page, page_size. Two requests collide iff every observable parameter matches. Successful ingest invalidates the cache so users see fresh prices.

To verify cache behavior in the running app: hit `/search?q=earbuds` twice — first response shows `cache_hit: false`, second shows `cache_hit: true` with sub-millisecond latency.

### Incremental price refresh

A separate scheduler job (`PRICE_REFRESH_MINUTES`, default 30) re-runs the same scraper but funnels the result through `refresh_prices` instead of `upsert_listings`:

- **No matcher.** Only listings already known by `(platform, platform_product_id)` are touched.
- **No new products.** Unknown listings are counted as `skipped` — the heavy ingest job is responsible for creation.
- **Optional staleness window.** `PRICE_REFRESH_MAX_AGE_HOURS` skips listings refreshed within that window, so a fresh full scrape isn't undone by an immediate refresh pass.

In production this would be replaced by a per-URL fetch (much cheaper than re-parsing a deals page); the mechanism in code is what matters for Phase 4.

### Resilience

Every scrape — full or refresh — is wrapped in:

1. **Exponential-backoff retry** with full jitter. `SCRAPER_RETRY_ATTEMPTS`, `SCRAPER_RETRY_BASE_DELAY_SECONDS`, `SCRAPER_RETRY_MAX_DELAY_SECONDS` control the policy.
2. **Per-platform circuit breaker.** After `BREAKER_FAILURE_THRESHOLD` consecutive failures the breaker opens and rejects calls fast for `BREAKER_COOLDOWN_SECONDS`; one probe call then either closes the breaker (success) or reopens it (failure). Other platforms keep running — this is the architectural "outage of one platform doesn't degrade the others" guarantee, hardened.

Breaker state is exposed at `/metrics` (`promosensei_circuit_breaker_state`).

### Observability

Two entry points:

- **Logs.** `setup_logging()` is called from `app.main` at startup. By default it emits one-line JSON: `{"ts", "level", "logger", "message", ...extras}`. Set `LOG_FORMAT=text` for human-readable local dev.
- **`/metrics`.** Hand-rolled Prometheus text format — counters, gauges, and histograms. Buckets on the latency histogram match the Phase 4 SLOs: 100 ms, 300 ms, 500 ms, 800 ms, 1.5 s, 3 s, 8 s.

Notable metrics:

| Metric | Type | Use |
|--------|------|-----|
| `promosensei_search_latency_ms` | histogram | p95 dashboard panel; SLO alert |
| `promosensei_cache_events_total` | counter | hit-rate over time (hit + miss labels) |
| `promosensei_scrape_outcomes_total` | counter | per-platform ok / partial / failed counts |
| `promosensei_price_refresh_total` | counter | listings touched by the refresher |
| `promosensei_circuit_breaker_state` | gauge | 0=closed, 1=half_open, 2=open (per platform) |
| `promosensei_cache_entries` | gauge | live cache depth |

`prometheus_client` was deliberately not pulled in — the registry is small and the text format is stable. Swap to upstream when scale demands richer features.

### Ranking eval harness

`app/eval/queries.yaml` holds 15 hand-labeled queries; `app/eval/harness.py` runs them through `search()` and aggregates NDCG@5, Precision@3, hit rate, and coverage.

Run it locally:

```bash
python scripts/run_eval.py            # text report, sorted by worst case first
python scripts/run_eval.py --json     # JSON for CI artefacts
```

The CI gate lives in `tests/test_eval_regression.py` and asserts:

- NDCG@5 ≥ `EVAL_MIN_NDCG_AT_5` (default 0.8)
- Precision@3 ≥ `EVAL_MIN_PRECISION_AT_3` (default 0.4)

These thresholds are calibrated against the **hashing** embedding provider on the seeded fixtures. Switch to `sentence-transformers` (or `openai`) and bump the thresholds upwards — the same harness works.

### Tests

```bash
cd phase4/backend
pytest -q
# 181 passed
```

Test breakdown:

- **Phase 3 carry-over**: 122 (matching, scraping, persistence, search service, health, …)
- **Phase 4 cache**: 17 (TTL, LRU, key stability, null cache, factory)
- **Phase 4 resilience**: 14 (retry, breaker state machine, registry)
- **Phase 4 observability**: 10 (JSON formatter, counters, histograms, gauges)
- **Phase 4 metrics endpoint**: 3 (exposition format, cache-stat surfacing, disable flag)
- **Phase 4 price refresh**: 5 (update, skip-unknown, max-age, cross-platform skip, run log)
- **Phase 4 search caching**: 4 (cold→warm, filter isolation, latency, manual invalidation)
- **Phase 4 eval**: 7 metrics + harness tests
- **Phase 4 eval regression**: 1 CI gate

## Frontend

Phase 4 layers a single visual addition over the Phase 3 UI: a **latency / cache-hit badge** next to the results count. Cached responses show a green `cached · 3 ms` pill; cold responses show `fresh · 412 ms`. Skeleton loaders carry over from Phase 3.

```bash
cd phase4/frontend
npm install
cp .env.example .env.local
npm run dev      # http://localhost:3000
```

## Edge cases handled in Phase 4

Pulled from [../docs/edge-cases.md](../docs/edge-cases.md) and the Phase 4 architecture goals:

- **Stale prices** → incremental refresher closes the gap between scrapes
- **Repeated identical queries** → cache amortises the embedding + DB cost
- **Per-platform outage** → breaker fails fast, other platforms keep running, `/health/scrapers` + `/metrics` surface the outage
- **Ranking regression on a code change** → CI eval gate catches it before merge
- **Cache poisoning across catalog updates** → ingest invalidates the cache after a successful upsert

Earlier phases' edge cases (1.x scraping, 2.x normalization, 3.x matching, 4.x query parsing, 5.x ranking/embedding) carry over unchanged.

## What's *not* in Phase 4

Deliberately deferred to keep the scope honest:

- **Loki / Grafana / OTel collectors.** Logs are JSON and `/metrics` is Prometheus text — wiring them up to a real backend is one config away, but no infra is shipped here.
- **Redis deployment.** The cache is Redis-ready (`CACHE_PROVIDER=redis` works), but the default and demo path stay in-process so the project runs with zero external services.
- **Per-URL price scraping.** The refresher reuses the deals scraper for the mechanism; production would replace this with a lighter per-listing fetch.
- **Real proxy pool.** Architecture.md mentions one alongside the breaker; current scrapers are fixture-driven, so this would be premature.
