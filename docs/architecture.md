# PromoSensei — Phase-Wise Architecture

This document breaks the build into four delivery phases. Each phase ships an end-to-end usable slice of the system, then layers in capability on top. The goal is to keep every phase **demonstrable**, **testable**, and **independently valuable** — not a frozen waterfall plan.

> Companion to [problemstatement.md](problemstatement.md).

---

## Phase Overview

| Phase | Theme | Outcome | Duration (est.) |
|-------|-------|---------|-----------------|
| **1** | Foundation & Data Ingestion | A working pipeline that scrapes one platform and serves keyword search | 2–3 weeks |
| **2** | Semantic Intelligence | Natural language queries powered by embeddings + vector search | 2 weeks |
| **3** | Cross-Platform Aggregation | All 3 platforms unified with deduplication and grouped results | 2–3 weeks |
| **4** | Real-Time, Scale & Polish | Freshness guarantees, caching, ranking tuning, production hardening | 2 weeks |

---

## Phase 1 — Foundation & Data Ingestion

**Goal:** prove the pipeline end-to-end with a single platform and basic keyword search.

### What ships

- Scraper for **one platform** (Amazon offers page).
- Normalized product schema persisted to a relational store.
- A minimal REST API that accepts a keyword query and returns matching products.
- A bare-bones web UI showing results in a list.

### Architecture

```
┌──────────────┐    HTTP    ┌──────────────┐    SQL     ┌──────────────┐
│   Web UI     │ ─────────► │  FastAPI     │ ─────────► │  PostgreSQL  │
│  (Next.js)   │ ◄───────── │  /search     │ ◄───────── │  products    │
└──────────────┘            └──────────────┘            └──────▲───────┘
                                                               │ INSERT
                                                        ┌──────┴───────┐
                                                        │ Amazon       │
                                                        │ Scraper Job  │
                                                        │ (cron, 1×/d) │
                                                        └──────────────┘
```

### Components

| Component | Technology | Responsibility |
|-----------|------------|----------------|
| Scraper | Python + Playwright / BeautifulSoup | Pull offer listings, normalize fields |
| Storage | PostgreSQL | Source-of-truth product catalog |
| API | FastAPI | `/search?q=...` returns matches via `ILIKE` |
| UI | Next.js | Search box + results list |
| Scheduler | Cron / APScheduler | Trigger scraper on a schedule |

### Exit criteria

- ✅ At least 500 Amazon products ingested with valid prices and discounts.
- ✅ `/search` returns relevant results in < 500 ms for keyword queries.
- ✅ End-to-end demo: type query → see results in browser.

---

## Phase 2 — Semantic Intelligence

**Goal:** replace keyword search with intent-aware semantic search.

### What ships

- Embedding generation for every product (title + key attributes).
- Vector database for similarity search.
- Query embedding pipeline at request time.
- Hybrid ranking: semantic similarity + price + rating.

### Architecture

```
┌──────────────┐         ┌──────────────────┐
│   Web UI     │ ──────► │   Query API      │
└──────────────┘         └────────┬─────────┘
                                  │
                    ┌─────────────┴─────────────┐
                    │                           │
            ┌───────▼────────┐         ┌────────▼────────┐
            │ Embedding Svc  │         │  Filter Service │
            │ (OpenAI /      │         │  price, rating  │
            │  sentence-     │         └────────┬────────┘
            │  transformers) │                  │
            └───────┬────────┘                  │
                    │ vector                    │
            ┌───────▼─────────────────┐         │
            │     Vector DB           │◄────────┘
            │  (Pinecone / pgvector)  │
            └─────────────────────────┘
                    ▲
                    │ upsert
            ┌───────┴────────┐
            │ Indexing Job   │ ◄── reads from PostgreSQL
            └────────────────┘
```

### Components

| Component | Technology | Responsibility |
|-----------|------------|----------------|
| Embedding model | `sentence-transformers/all-MiniLM-L6-v2` *or* OpenAI `text-embedding-3-small` | Convert text to vectors |
| Vector store | **pgvector** (extends Phase 1 Postgres) — Pinecone if scale demands it | Similarity search |
| Indexing job | Python worker | Embed new/changed products, upsert to vector store |
| Ranker | Custom Python module | Blend cosine score + normalized discount + rating |

### Ranking formula (initial)

```
score = 0.6 × cosine_similarity
      + 0.2 × normalized_discount
      + 0.2 × normalized_rating
```

Tunable via config; revisit in Phase 4.

### Exit criteria

- ✅ Query *"good earbuds under ₹2000"* returns earbuds (not phone cases).
- ✅ p95 query latency under 800 ms including embedding generation.
- ✅ A/B test vs Phase 1 keyword search shows higher click-through on top result.

---

## Phase 3 — Cross-Platform Aggregation

**Goal:** treat the catalog as a unified product graph, not three siloed feeds.

### What ships

- Scrapers for **Flipkart** and **Nykaa**.
- Product matching: identify when the same product appears on multiple platforms.
- Grouped result view in the UI ("This product on 3 platforms — best price ₹1,899").
- Per-platform health monitoring.

### Architecture

```
                    ┌──────────────────────────┐
                    │     Scraper Pool         │
                    │  ┌─────┐ ┌─────┐ ┌─────┐ │
                    │  │ AMZ │ │ FLP │ │ NYK │ │
                    │  └──┬──┘ └──┬──┘ └──┬──┘ │
                    └─────┼───────┼───────┼────┘
                          ▼       ▼       ▼
                    ┌──────────────────────────┐
                    │   Ingestion Queue        │
                    │   (Redis / SQS)          │
                    └────────────┬─────────────┘
                                 ▼
                    ┌──────────────────────────┐
                    │   Normalizer + Matcher   │
                    │  ┌────────────────────┐  │
                    │  │ Title cleaner      │  │
                    │  │ Brand extractor    │  │
                    │  │ Fuzzy match (RapidFuzz) │
                    │  │ Embedding match    │  │
                    │  └────────────────────┘  │
                    └────────────┬─────────────┘
                                 ▼
                    ┌──────────────────────────┐
                    │   Canonical Product DB   │
                    │   product ─< listings    │
                    └────────────┬─────────────┘
                                 ▼
                    ┌──────────────────────────┐
                    │   Vector Index           │
                    │   (one entry per         │
                    │   canonical product)     │
                    └──────────────────────────┘
```

### Schema evolution

```
products (canonical)
├── id
├── canonical_title
├── brand
├── category
└── primary_image_url

listings (per-platform)
├── id
├── product_id  ──► products.id
├── platform    (amazon | flipkart | nykaa)
├── platform_product_id
├── price
├── original_price
├── discount
├── rating
├── url
└── last_seen_at
```

### Components

| Component | Technology | Responsibility |
|-----------|------------|----------------|
| Queue | Redis / SQS | Decouple scraping from processing |
| Matcher | RapidFuzz + embedding cosine | Cluster listings into canonical products |
| Health monitor | Prometheus + Grafana | Track per-scraper success rate, freshness |

### Exit criteria

- ✅ ≥ 70% of listings successfully matched to a canonical product across platforms.
- ✅ UI surfaces grouped products with per-platform price comparison.
- ✅ Each scraper exposes uptime + success-rate metrics.

---

## Phase 4 — Real-Time, Scale & Polish

**Goal:** make the system feel **fast, fresh, and trustworthy**.

### What ships

- Caching layer for hot queries.
- Incremental scraping (price-only refresh, much higher frequency).
- Ranking-quality evaluation harness.
- Rate-limit handling, retry, and circuit-breaker logic.
- Observability: logs, metrics, traces.

### Architecture

```
                              ┌─────────────────┐
                              │   CDN / Edge    │
                              └────────┬────────┘
                                       ▼
                              ┌─────────────────┐
                              │   API Gateway   │
                              │   + Rate Limit  │
                              └────────┬────────┘
                                       ▼
                              ┌─────────────────┐
                              │  Query Service  │
                              └──┬──────────┬───┘
                                 │          │
                  ┌──────────────▼─┐    ┌───▼────────────┐
                  │ Redis Cache    │    │ Vector DB      │
                  │ (hot queries,  │    │ (canonical     │
                  │  TTL 5 min)    │    │  products)     │
                  └────────────────┘    └────────────────┘

         ┌──────────────────────────────────────────────────┐
         │              Ingestion Tier                      │
         │                                                  │
         │  ┌─────────────────┐    ┌──────────────────┐     │
         │  │ Full Scrape     │    │ Price-Only Refresh│    │
         │  │ daily, deep     │    │ every 30 min,     │    │
         │  │                 │    │ light             │    │
         │  └─────────────────┘    └──────────────────┘     │
         │                                                  │
         │  Circuit breaker · Retry w/ backoff · Proxy pool │
         └──────────────────────────────────────────────────┘

         ┌──────────────────────────────────────────────────┐
         │           Observability                          │
         │  Logs (Loki) · Metrics (Prometheus) · Traces (OTel) │
         └──────────────────────────────────────────────────┘
```

### Key additions

| Capability | Mechanism |
|------------|-----------|
| **Freshness** | Lightweight price refresher hits product URLs every 30 min |
| **Latency** | Redis caches top-1000 queries; cache key includes filters |
| **Resilience** | Circuit breakers per-platform; failures don't block other platforms |
| **Quality** | Offline eval set (50 labeled queries) regressed on every ranking change |
| **Operability** | Structured logs, scraper SLOs, alerting on freshness lag |

### Exit criteria

- ✅ p95 query latency < 300 ms for cached queries, < 800 ms cold.
- ✅ Listed prices reflect platform price within 1 hour for 95% of products.
- ✅ Per-platform scraper outage does **not** degrade the other platforms.
- ✅ Ranking eval suite runs in CI; merges blocked on regression.

---

## Cross-Cutting Concerns

These run alongside every phase, not after.

| Concern | Approach |
|---------|----------|
| **Compliance** | Respect `robots.txt`; throttle scrapers; prefer official APIs where offered |
| **Security** | No PII stored in Phase 1–3; secrets in env / vault, never in repo |
| **Testing** | Unit tests for normalizers; integration tests against fixture HTML; eval suite for ranking |
| **CI/CD** | GitHub Actions: lint → test → build → deploy to staging on merge to `main` |
| **Cost** | Track embedding API spend; switch to local model if monthly cost > threshold |

---

## Technology Summary

| Layer | Phase 1 | Phase 2 | Phase 3 | Phase 4 |
|-------|---------|---------|---------|---------|
| Frontend | Next.js | Next.js | Next.js + grouped views | Next.js + skeleton loaders |
| API | FastAPI | FastAPI | FastAPI | FastAPI behind gateway |
| DB | PostgreSQL | PostgreSQL + pgvector | PostgreSQL + pgvector | + Redis cache |
| Workers | Cron | Cron | Queue-driven | Tiered (full + delta) |
| Scrapers | Playwright (Amazon) | — | + Flipkart, Nykaa | + proxy pool, circuit breaker |
| Observability | Stdout logs | Stdout logs | Prometheus | Loki + Prom + OTel |

---

## Out of Roadmap (Future Phases)

These are intentionally deferred and called out so they don't sneak into earlier phases:

- User accounts, wishlists, price-drop alerts.
- Mobile native apps (iOS/Android).
- Additional platforms (Myntra, Ajio, BigBasket, etc.).
- Personalized ranking based on user history.
- Browser extension for in-page deal overlays.
