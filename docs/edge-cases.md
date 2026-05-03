# PromoSensei — Edge Cases & Failure Modes

Companion to [problemstatement.md](problemstatement.md) and [architecture.md](architecture.md).

This doc enumerates the realistic ways PromoSensei will misbehave in production. Every edge case is paired with a **detection signal**, a **handling strategy**, and the **phase** in which it should be addressed. Treat this as a living checklist for design reviews, code reviews, and QA.

---

## Legend

| Symbol | Meaning |
|--------|---------|
| 🔴 | Blocks core flow — must handle |
| 🟡 | Degrades quality — should handle |
| 🟢 | Cosmetic / rare — nice to handle |

---

## 1. Data Ingestion & Scraping

### 1.1 Platform layout changes 🔴
**Scenario:** Amazon/Flipkart/Nykaa changes their HTML structure; selectors break overnight.
**Detection:** Sudden drop in scraped-product count (> 50% below 7-day average).
**Handling:**
- Per-scraper success-rate metric with alert at < 80%.
- Schema validation on every scraped row — reject and log if required fields are null.
- Maintain CSS selector + XPath as fallback pairs.
- Snapshot raw HTML on failure for offline diagnosis.
**Phase:** 1 (basic), hardened in 4.

### 1.2 IP bans and rate limiting 🔴
**Scenario:** Platform returns 429 / 503 or silently throttles after N requests.
**Handling:**
- Exponential backoff with jitter.
- Rotating proxy pool (residential proxies for stricter platforms).
- Per-platform request budget (req/min).
- Circuit breaker: pause scraper for 30 min after 5 consecutive 429s.
**Phase:** 4.

### 1.3 CAPTCHA challenges 🟡
**Scenario:** Bot-detection serves a CAPTCHA instead of product data.
**Handling:**
- Detect via response signature (CAPTCHA HTML markers).
- Mark scrape job as failed and pause that worker.
- Fall back to cached data; alert on prolonged outage.
- Do **not** auto-solve — both legally fraught and unreliable.

### 1.4 JavaScript-rendered content 🟡
**Scenario:** Prices/ratings load via XHR after initial HTML.
**Handling:** Use Playwright / headless Chromium with `wait_for_selector` on the price element. Fall back to network-level interception of the JSON XHR when feasible (faster + more stable than DOM scraping).

### 1.5 Geo-restricted content 🟡
**Scenario:** Product is visible in IN but not from a US-based scraper IP.
**Handling:** Pin scraper egress IPs to India region; assert `currency == INR` in normalizer.

### 1.6 Login / age walls 🟢
**Scenario:** Some Nykaa categories or A+ Amazon pages require login.
**Handling:** Skip those listings in Phase 1–3; revisit only if they're high-value categories.

### 1.7 Pagination breakage 🟡
**Scenario:** Infinite scroll, "Next" link removed, or page numbers stop at 7 even when 20 pages exist.
**Handling:**
- Detect end-of-results by content (e.g., empty product grid) **and** by page-count guard (max 100 pages).
- Cross-check expected listing count from result-header text vs pages crawled.

### 1.8 Sponsored / ad listings 🟡
**Scenario:** Sponsored products inflate result counts and pollute rankings.
**Handling:** Detect sponsored markers in DOM and either drop or flag with `is_sponsored: true`. Default UI hides sponsored.

### 1.9 Out-of-stock products with stale prices 🟡
**Scenario:** Listing still appears but item is unavailable; price field may be missing or zero.
**Handling:** Detect via stock signal (button text, `availability` schema). Set `in_stock: false` and de-prioritize in ranking.

### 1.10 Robots.txt and ToS conflicts 🔴
**Scenario:** Platform updates `robots.txt` to disallow `/deals/*`.
**Handling:** Honor robots; switch to official affiliate API where available; document compliance posture in `COMPLIANCE.md`.

---

## 2. Data Quality & Normalization

### 2.1 Missing required fields 🔴
**Scenario:** Price field absent, rating missing, image broken.
**Handling:**
- Required: `title`, `price`, `url`, `platform` — reject row if any are null.
- Optional: `rating`, `original_price`, `image` — accept null and degrade UI gracefully.

### 2.2 Inconsistent price formatting 🟡
**Scenario:** `₹1,999`, `Rs. 1999`, `INR 1,999.00`, `1999/-`.
**Handling:** Normalizer strips currency symbols, thousands separators, and trailing `/-`; converts to `Decimal` (never `float` for money). Reject if multiple decimal points or non-numeric remnants.

### 2.3 Discount math doesn't add up 🟡
**Scenario:** Listed discount = 60%, but `(original - current) / original = 38%`.
**Handling:**
- **Trust computed value, not the labeled one.** Recompute discount in normalizer.
- Flag rows where labeled vs computed differ by > 5% for spot-checking.

### 2.4 Original price ≤ current price 🟡
**Scenario:** Bad scrape captures sale price as both fields, yielding 0% discount.
**Handling:** If `original_price <= price`, set `original_price = null` and `discount = 0`.

### 2.5 Implausible discount values 🔴
**Scenario:** 95% off a ₹50,000 laptop — likely a price-extraction bug.
**Handling:** Soft-cap discount display at 90%; route rows with > 90% discount through a **review queue** before they appear in search.

### 2.6 Duplicate listings on same platform 🟡
**Scenario:** Same Amazon ASIN appears under multiple seller listings.
**Handling:** Dedupe by `platform_product_id` (ASIN, FSN, SKU). Keep the lowest-price, in-stock listing.

### 2.7 Multi-variant products 🟡
**Scenario:** "iPhone 15 — 128GB / 256GB / 512GB" each have separate prices.
**Handling:** Treat each variant as its own listing with `variant_attrs: {storage: "128GB"}`. Do not collapse.

### 2.8 Title noise 🟢
**Scenario:** `"(Sponsored) [Limited Deal!] Apple iPhone 15..."`.
**Handling:** Title cleaner strips common noise patterns (`Sponsored`, `Limited Deal`, `Best Seller`, brackets, emoji) before embedding generation. Keep raw title in `raw_title` for debugging.

### 2.9 Currency / locale mix-ups 🟢
**Scenario:** Imported product page shows USD instead of INR.
**Handling:** Normalizer asserts `INR`. Reject if currency is anything else.

---

## 3. Cross-Platform Matching

### 3.1 Same product, different titles 🟡
**Scenario:**
- Amazon: `"Sony WH-1000XM5 Wireless Noise Cancelling Headphones, Black"`
- Flipkart: `"Sony WH1000XM5 Bluetooth Headset Black"`

**Handling:** Match using a hybrid signal:
1. Brand + model number extraction (regex).
2. Embedding cosine similarity > 0.85.
3. Image perceptual hash overlap (Phase 4+).
4. Price within ±15% sanity check.

### 3.2 Different products, similar titles 🟡
**Scenario:** `"Sony WH-1000XM4"` and `"Sony WH-1000XM5"` differ by one digit.
**Handling:** Model-number extractor weighted heavily; suffix mismatch should override title similarity.

### 3.3 Bundle vs single 🟡
**Scenario:** `"iPhone 15 + AirPods Combo"` matched to `"iPhone 15"`.
**Handling:** Detect bundle keywords (`combo`, `pack of`, `bundle`, `with case`) and treat as separate canonical product.

### 3.4 Refurbished / renewed 🟡
**Scenario:** "Renewed" iPhone matched to new iPhone, distorting price comparison.
**Handling:** Detect condition markers; store `condition: new | renewed | used` and only group within the same condition.

### 3.5 Pack-size confusion 🟡
**Scenario:** `"Cetaphil Cleanser 250ml"` vs `"Cetaphil Cleanser 500ml"` grouped as one product.
**Handling:** Extract size/quantity (`\d+\s*(ml|g|kg|pack)`) into a structured field; require match for grouping.

### 3.6 Multiple sellers, same product 🟢
**Scenario:** Amazon shows 5 sellers for the same ASIN.
**Handling:** Take the Buy-Box price. Optionally surface seller diversity later.

---

## 4. Query & Search

### 4.1 Empty query 🔴
**Handling:** Return curated trending deals; do **not** return random products. Prevent embedding a blank string.

### 4.2 Extremely long queries 🟡
**Scenario:** User pastes a 5000-char product spec sheet.
**Handling:** Truncate to first 512 tokens before embedding; surface a soft warning.

### 4.3 Non-English / Hinglish queries 🟡
**Scenario:** `"sasta phone under 10k"`, `"अच्छा मॉइस्चराइज़र"`.
**Handling:** Use a multilingual embedding model (e.g., `paraphrase-multilingual-MiniLM`). For numeric extraction, support common Hinglish patterns (`10k`, `2k`, `dus hazaar`).

### 4.4 Typos and misspellings 🟡
**Scenario:** `"sumsung galxy"`.
**Handling:** Embeddings handle most fuzzy cases. Add a query-spell-correction pass (SymSpell with a brand+product lexicon) if eval shows degraded results.

### 4.5 Numeric constraints in natural language 🔴
**Scenario:** `"earbuds under 2000"`, `"between 5k and 10k"`, `"4-star rated below ₹3000"`.
**Handling:** Pre-parse query for numeric/comparison patterns and extract structured filters before embedding the rest. Apply as post-filters on the vector results.

### 4.6 Negation 🟡
**Scenario:** `"laptop not Apple"`, `"phone without notch"`.
**Handling:** Phase 4 — fine-tuned intent parser or LLM-based query rewriter. Phase 1–3: best-effort, document the limitation.

### 4.7 Brand-only queries 🟡
**Scenario:** `"Nike"` returns 800 products with no clear top.
**Handling:** Default sort by combined discount + rating. Surface category facets (shoes, apparel, accessories).

### 4.8 No-result queries 🟡
**Scenario:** `"vintage Soviet typewriter"`.
**Handling:** Show "No matches" with suggested broader queries derived from query embeddings nearest to popular categories.

### 4.9 Adversarial input 🔴
**Scenario:** SQL injection (`' OR 1=1 --`), prompt injection (`ignore prior instructions and...`).
**Handling:**
- Parameterized queries everywhere; never string-concat into SQL.
- Strip control chars; cap length.
- LLM features (if any) must treat user query as data, not instruction — wrap in clearly delimited input blocks.

### 4.10 Profanity / abusive queries 🟢
**Handling:** Allow but suppress in trending/popular-query analytics. Don't log raw query if it contains PII patterns.

---

## 5. Embeddings & Vector Search

### 5.1 Cold start with empty index 🔴
**Scenario:** First deploy, vector DB has 0 entries.
**Handling:** API returns a helpful message (`"Catalog is being built — try again in a few minutes"`) instead of an empty array.

### 5.2 Embedding model upgrade 🟡
**Scenario:** Switching from MiniLM to a newer model — old vectors are incomparable to new query vectors.
**Handling:**
- Versioned index (`products_v2`).
- Dual-write during migration; cutover only after backfill complete.
- Never mix vectors of different dimensions or models.

### 5.3 Stale embeddings after product update 🟡
**Scenario:** Title or description changes; embedding reflects the old text.
**Handling:** Re-embed on `title_hash` change. Job runs incrementally on every catalog refresh.

### 5.4 Vector DB outage 🔴
**Handling:** Fall back to keyword search via Postgres full-text index. UI shows a banner `"Limited results — semantic search degraded"`.

### 5.5 Embedding API rate limit 🟡
**Scenario:** OpenAI returns 429 during a large batch indexing job.
**Handling:** Exponential backoff; queue persistence so the job resumes; alert if backlog grows for > 1 hour.

### 5.6 Embedding API cost spike 🟡
**Handling:** Daily spend dashboard; auto-switch to local `sentence-transformers` model if 24h spend exceeds threshold.

---

## 6. Ranking

### 6.1 Tied scores 🟢
**Handling:** Deterministic tiebreak by `product_id` so result order is stable across requests.

### 6.2 New products with no rating 🟡
**Handling:** Treat null rating as the **median** rating of the category (Bayesian smoothing), not as 0 — otherwise new launches are unfairly buried.

### 6.3 Outlier discounts skewing normalization 🟡
**Scenario:** One 99% discount inflates the normalization denominator, shrinking everyone else's contribution.
**Handling:** Winsorize discount at the 95th percentile before normalization.

### 6.4 Category-blind ranking 🟡
**Scenario:** Earbuds and headphones compete on the same query because both match well.
**Handling:** Phase 4 — category-aware reranker using a small classifier on the query.

---

## 7. Pricing & Freshness

### 7.1 Price changed after cache hit 🟡
**Scenario:** User clicks through, lands on platform showing a different price.
**Handling:**
- Show `last_updated` timestamp next to price (`"as of 12 min ago"`).
- Aggressively short cache TTL for the price refresher (≤ 30 min).
- On click, re-fetch live price and reconcile (Phase 4).

### 7.2 Flash deals expire mid-session 🟡
**Handling:** Surface deal expiry when scraped (`offer_ends_at`); hide expired deals from results immediately.

### 7.3 Coupon-required prices 🟡
**Scenario:** Listed price ₹999 only after applying coupon `SAVE20`.
**Handling:** Store both `display_price` and `effective_price`; show the coupon code prominently. Don't lie about the headline price.

### 7.4 Bank-offer / member prices 🟡
**Handling:** Always store the **publicly visible non-conditional price**. Note bank/Prime offers in a `notes` field but don't include them in primary discount calc.

### 7.5 Out-of-stock between scrape and click 🟢
**Handling:** On click, check `last_seen_in_stock`; if > 6 hours old, prompt UI to reverify before redirect.

---

## 8. Infrastructure & Reliability

### 8.1 One platform scraper down 🔴
**Handling:** Scrapers are independent; aggregation layer treats missing platform as `n/a` rather than failing the request. UI shows `"Flipkart unavailable"` chip.

### 8.2 Database connection pool exhaustion 🔴
**Handling:** PgBouncer in front of Postgres; per-request statement timeout (5s). Retries on transient `5xx`.

### 8.3 Cache stampede on hot query 🟡
**Scenario:** Popular query expires; 1000 concurrent requests all rebuild it.
**Handling:** Single-flight pattern (only one request rebuilds; others wait); soft-TTL with background refresh.

### 8.4 Indexing job vs read traffic contention 🟡
**Handling:** Run heavy embedding jobs against a read replica; throttle index writes during peak hours.

### 8.5 Partial scraper success 🟡
**Scenario:** Pages 1–7 succeed, page 8 fails. Do we keep partial data?
**Handling:** Yes — write per-page, not per-job. Mark job as `partial` for observability.

### 8.6 Concurrent updates to same product 🟢
**Handling:** Last-write-wins via `updated_at` comparison; no row-level locking needed.

### 8.7 Time zone drift 🟢
**Handling:** Store all timestamps in UTC; convert to IST only at the UI layer.

---

## 9. Security & Compliance

### 9.1 Secrets in scraper config 🔴
**Handling:** Proxy creds, API keys via env vars / secrets manager only. Pre-commit hook to block hardcoded keys.

### 9.2 Scraping ToS exposure 🔴
**Handling:** Document compliance posture; prefer official affiliate APIs where they exist; honor `robots.txt`; rate-limit voluntarily even if not enforced.

### 9.3 Logging PII 🟡
**Handling:** Don't log raw user queries with potential PII (emails, phone numbers). Hash or redact in logs.

### 9.4 Affiliate disclosure 🟡
**Handling:** If using affiliate links, surface disclosure in footer per FTC/India ASCI norms.

### 9.5 DMCA / image rights 🟢
**Handling:** Hot-link images from origin platforms rather than mirroring. If mirroring becomes necessary, take down on request within 24h.

---

## 10. UX Edge Cases

### 10.1 Filter combination yields zero results 🟡
**Scenario:** "Headphones, ₹100–₹200, ≥4★, Nykaa only."
**Handling:** Show "No matches" with one-click suggestions to relax the most restrictive filter.

### 10.2 Slow first-load on cold cache 🟡
**Handling:** Skeleton screens + streamed results; first product visible within 200 ms even if full ranking takes longer.

### 10.3 Image fails to load 🟢
**Handling:** Placeholder with platform logo. Don't break layout.

### 10.4 Product link 404s after click 🟢
**Handling:** Track redirect-failure rate per platform; auto-prune URLs that 404 twice in 24h.

### 10.5 Mobile narrow viewports 🟢
**Handling:** Group view collapses to stacked cards; price comparison becomes a tap-to-expand row.

### 10.6 Right-to-left or unusual scripts in titles 🟢
**Handling:** UI uses `dir="auto"` on title elements.

---

## 11. Testing Coverage Matrix

| Layer | Edge cases covered by |
|-------|----------------------|
| Scraper | Fixture HTML snapshots (one per platform per layout version); replay tests |
| Normalizer | Unit tests with malformed inputs (missing fields, weird currencies, negative discounts) |
| Matcher | Curated 100-pair labeled set (positive/negative match examples) |
| Ranker | 50-query eval set with annotated relevance; tracked in CI |
| API | Contract tests for empty query, oversize query, injection attempts |
| End-to-end | Synthetic browse flows hitting all three platforms weekly |

---

## 12. Open Questions

Items that need product/legal decisions before they can be resolved:

- [ ] Are we using **affiliate APIs** for any platform? (Affects compliance posture and price freshness.)
- [ ] How do we handle **price errors** that look like glitches (e.g., ₹500 laptop) — auto-hide or display with a warning?
- [ ] **Retention policy** for scraped data — how long do we keep historical prices for trend graphs?
- [ ] **Geographic scope** — India-only, or do we plan international ops? (Drives currency, compliance, proxy decisions.)
- [ ] **Personalization data** — if/when we add accounts, what's stored vs computed-on-demand?
