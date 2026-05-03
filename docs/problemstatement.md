# PromoSensei — AI-Powered Cross-Platform Offer Discovery System

## 1. Overview

Online shoppers routinely hunt for discounted products across multiple e-commerce platforms — Amazon, Flipkart, Nykaa, and others. The current experience is fragmented and inefficient: each platform has its own search interface, its own offer pages, and its own ranking logic, none of which understand what the user actually means when they type a query.

**PromoSensei** is a unified, AI-powered offer discovery system that lets users describe what they want in natural language and instantly see the best deals across platforms — ranked by relevance, price, and rating.

---

## 2. Problem Statement

Today's offer discovery is broken in five concrete ways:

| # | Problem | Impact |
|---|---------|--------|
| 1 | Offers are scattered across platforms with no central view | Users open 5–10 tabs to compare a single product |
| 2 | Search is keyword-based, not intent-based | Queries like *"good budget earbuds with mic"* return poor matches |
| 3 | No standardized cross-platform product matching | The same product appears under different titles, making comparison hard |
| 4 | Manual price and rating comparison is tedious | Users either give up or settle for a suboptimal deal |
| 5 | Deal data is rarely real-time | Stale prices and expired offers erode trust |

The result: **wasted time, missed deals, and poor purchase decisions.**

---

## 3. Objectives

### Primary Objective

Build a unified system that:

- Accepts **natural language queries** from users.
- Uses **semantic search** to understand intent beyond keywords.
- Retrieves **active offers** from multiple e-commerce platforms in near real-time.
- Presents a **consolidated, comparable view** of results.

### Secondary Objectives

- Cut product-discovery time by eliminating multi-tab browsing.
- Improve relevance through embedding-based semantic matching.
- Enable side-by-side cross-platform price comparison.
- Support filtering and sorting by price, discount, and rating.
- Keep deal data fresh through periodic ingestion.

---

## 4. Scope

### In Scope

**Supported Platforms (Phase 1)**
- Amazon
- Flipkart
- Nykaa

**Input**
- Natural language queries
  *e.g., "best wireless earbuds under ₹2000", "skincare deals for oily skin"*

**Output**
For every matched product:
- Product title
- Current price & original price
- Discount percentage
- User rating
- Source platform
- Direct product URL
- Grouped view when the same product is found on multiple platforms

### Out of Scope (Phase 1)

- Checkout / purchase flow
- User accounts, wishlists, or notifications
- Platforms beyond the three listed above
- Mobile native apps

---

## 5. System Workflow

### 5.1 Data Ingestion Layer

Responsible for collecting raw deal data from each supported platform.

- Scrape offers/deals pages or use official APIs where available.
- Normalize titles, prices, and ratings into a consistent schema.
- Deduplicate near-identical listings.
- Persist results to the product store on a recurring schedule.

**Normalized Product Schema**

```json
{
  "product_id": "string",
  "title": "string",
  "price": 0.0,
  "original_price": 0.0,
  "discount": 0.0,
  "rating": 0.0,
  "platform": "string",
  "url": "string"
}
```

### 5.2 Semantic Indexing Layer

- Generate vector embeddings for each product title + description.
- Store embeddings in a vector database for fast similarity search.
- Refresh embeddings whenever the underlying catalog changes.

### 5.3 Query & Retrieval Layer

- Convert the user's natural language query into an embedding.
- Run a top-k similarity search against the product index.
- Apply user-supplied filters (price range, rating, platform).
- Rank by a weighted combination of relevance, discount, and rating.

### 5.4 Aggregation & Presentation Layer

- Group identical or near-identical products across platforms.
- Surface the best deal per product.
- Return a structured response to the client UI.

---

## 6. Success Criteria

The system is considered successful if it:

- Returns relevant results for **≥ 90%** of natural language test queries.
- Aggregates deals from **all three** target platforms in a single response.
- Reflects price changes within **≤ 1 hour** of platform updates.
- Reduces a user's typical product-discovery time to **under 30 seconds**.

---

## 7. Constraints & Assumptions

- Public offer pages remain scrape-friendly or expose usable APIs.
- Platforms do not aggressively rate-limit ingestion jobs.
- All prices are in INR; multi-currency support is deferred.
- The MVP runs as a web application; no native mobile build is required.

---

## 8. High-Level Architecture

```
        ┌──────────────┐
        │   User UI    │
        └──────┬───────┘
               │ NL Query
        ┌──────▼───────┐
        │  Query API   │
        └──────┬───────┘
               │
   ┌───────────▼───────────┐
   │  Semantic Search +    │
   │   Ranking Engine      │
   └───────────┬───────────┘
               │
        ┌──────▼───────┐
        │  Vector DB   │◄───── Embedding Job
        └──────┬───────┘
               │
        ┌──────▼───────┐
        │ Product Store│◄───── Ingestion Workers
        └──────────────┘            │
                            ┌───────┴────────┐
                         Amazon  Flipkart  Nykaa
```
