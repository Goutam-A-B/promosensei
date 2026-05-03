# PromoSensei

> Semantic deal search across Amazon, Flipkart, and Nykaa — with grouped results, hot-query caching, incremental price refresh, per-platform circuit breakers, structured logs, Prometheus metrics, and a CI ranking-quality gate.

[![CI](https://github.com/Goutam-A-B/promosensei/actions/workflows/ci.yml/badge.svg)](https://github.com/Goutam-A-B/promosensei/actions/workflows/ci.yml)

🌐 **Live demo:** [**promosensei.vercel.app**](https://promosensei.vercel.app)  ·  📖 **How it works:** [promosensei.vercel.app/about](https://promosensei.vercel.app/about)  ·  🧪 **Test count:** 181 passing

---

## What this is

PromoSensei is a four-phase build of a cross-platform deal engine. You type *"noise cancelling headphones"* and get one card per real-world product with a per-platform price ladder underneath — instead of three nearly-identical results from three different sites.

It's designed as a **portfolio project** that demonstrates engineering across the stack: scraping, normalisation, fuzzy + semantic matching, hybrid search, caching, observability, resilience, and a CI ranking-quality gate.

```
┌──────────────┐    ┌─────────────┐    ┌─────────────┐
│  Scrapers    │ ─► │  Matcher    │ ─► │  Canonical  │
│  AMZ FLP NYK │    │  brand+model│    │  Product DB │
└──────────────┘    │  +fuzz+cos  │    └──────┬──────┘
                    └─────────────┘           │
                                              ▼
              ┌───────────┐    ┌────────────┐    ┌──────────┐
              │ Web UI    │ ─► │  /search   │ ─► │  Ranker  │
              │ (Next.js) │ ◄─ │  cached    │ ◄─ │ sim+disc │
              └───────────┘    └─────┬──────┘    └──────────┘
                                     │
                              ┌──────┴──────┐
                              │ /metrics    │  Prometheus
                              │ /health/*   │  scrape target
                              └─────────────┘
```

## The four phases

Each phase is a self-contained directory you can run on its own. They build on each other, so reading them in order shows the engineering progression.

| Phase | Theme | What it ships |
|-------|-------|---------------|
| [phase1/](phase1) | **Foundation** | Single-platform Amazon scraper · keyword search · minimal Next.js UI |
| [phase2/](phase2) | **Semantic intelligence** | Embedding pipeline · pluggable provider (hashing / sentence-transformers / OpenAI) · hybrid ranking |
| [phase3/](phase3) | **Cross-platform aggregation** | Flipkart + Nykaa scrapers · canonical-product matcher · grouped results · `/health/scrapers` |
| [phase4/](phase4) | **Real-time, scale & polish** | Hot-query cache · incremental price refresh · retry + circuit breakers · JSON logs · `/metrics` · NDCG eval harness with CI gate |

The live demo runs **phase 4** ([phase4/README.md](phase4/README.md)).

## Highlights worth a 60-second skim

**Cross-platform matcher with hard merge guards.** A bundle SKU, a refurbished SKU, or a 250 ml SKU never collapses into the 500 ml original — the matcher *blocks* merges on size mismatch, refurbished flag, bundle flag, and ±25 % price sanity before any fuzz score is even computed. False splits are recoverable; false merges corrupt canonical product identity. *([phase4/backend/app/matching/](phase4/backend/app/matching/))*

**Listing-level filtering with product-level grouping.** "Earbuds under ₹2 000" surfaces a product whose Amazon listing is overpriced if its Flipkart listing fits — one card, with the cheap listing highlighted. The naive approach drops the whole product. *([phase4/backend/app/search_service.py](phase4/backend/app/search_service.py))*

**CI ranking-quality gate.** 15 hand-labelled queries with NDCG@5 and Precision@3 thresholds — merges fail if either metric regresses. Hand-rolled metric implementations (no scikit-learn just to compute three numbers). *([phase4/backend/app/eval/](phase4/backend/app/eval/))*

**Observability without vendor lock-in.** Logs are line-delimited JSON, `/metrics` is Prometheus text format. The metrics registry (counters, gauges, histograms) is hand-rolled to avoid pulling in `prometheus_client` for a handful of values. *([phase4/backend/app/observability/](phase4/backend/app/observability/))*

**Per-platform circuit breakers.** A Flipkart outage doesn't take Amazon and Nykaa with it; the breaker also stops us from hammering a dead platform. Three-state (CLOSED / OPEN / HALF_OPEN) with injectable clock so it's fully unit-testable. *([phase4/backend/app/resilience/](phase4/backend/app/resilience/))*

## Run it locally

```bash
# Backend
cd phase4/backend
python -m venv .venv && .venv\Scripts\activate    # PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
python scripts/seed_demo.py --reset               # seed ≈120 curated products
uvicorn app.main:app --reload                     # http://localhost:8000

# Frontend (in a second terminal)
cd phase4/frontend
npm install
cp .env.example .env.local
npm run dev                                       # http://localhost:3000
```

```bash
# Run the eval harness
cd phase4/backend
python scripts/run_eval.py            # NDCG@5, Precision@3, hit rate, coverage

# Run the test suite
pytest -q                              # 181 passing
```

## Deploy your own copy

See [DEPLOY.md](DEPLOY.md) for click-by-click instructions on the **fully free** deploy path:

- **Frontend:** Vercel hobby tier
- **Backend:** Render free web service
- **DB:** Neon free Postgres

Total cost: ₹0 / month. None require a credit card.

## Stack

**Backend** · FastAPI · SQLAlchemy 2.0 · Pydantic v2 · APScheduler · RapidFuzz · BeautifulSoup · Playwright · pytest

**Frontend** · Next.js 14 (App Router) · React · TypeScript · Tailwind CSS

**Data** · PostgreSQL (Neon) · in-process JSON-vector index (pgvector swap documented)

**Ops** · Docker · GitHub Actions CI · Prometheus text exposition · structured JSON logs

## Documentation

- [docs/architecture.md](docs/architecture.md) — full four-phase plan with per-phase exit criteria
- [docs/edge-cases.md](docs/edge-cases.md) — the failure-mode catalogue every phase tests against
- [docs/problemstatement.md](docs/problemstatement.md) — the original problem framing
- [DEPLOY.md](DEPLOY.md) — free-tier deploy guide
