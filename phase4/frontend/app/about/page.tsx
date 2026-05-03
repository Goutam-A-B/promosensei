import Link from "next/link";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "How PromoSensei works",
  description:
    "Architecture, design choices, and what's real vs. demoed in PromoSensei — a portfolio project by Goutam Edith.",
};

export default function AboutPage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col gap-8 px-4 py-10">
      <header className="flex items-baseline justify-between">
        <h1 className="text-3xl font-bold tracking-tight">How it works</h1>
        <Link
          href="/"
          className="text-sm text-slate-500 underline-offset-4 hover:text-slate-900 hover:underline"
        >
          ← Back to search
        </Link>
      </header>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">The problem</h2>
        <p className="text-slate-700">
          The same product is sold across Amazon, Flipkart, and Nykaa under three subtly different
          titles, often at three different prices. Existing comparison tools rely on brittle exact
          matches and miss obvious near-duplicates. PromoSensei is a four-phase build of a
          cross-platform deal engine that fixes this — you type{" "}
          <em>&ldquo;noise cancelling headphones&rdquo;</em>, it returns the canonical product with
          a per-platform price ladder.
        </p>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">The pipeline</h2>
        <ol className="list-decimal space-y-2 pl-5 text-slate-700">
          <li>
            <strong>Scrape</strong> — three Playwright + BeautifulSoup scrapers, one per platform,
            funnel into a normalised <code>ScrapedListing</code> shape.
          </li>
          <li>
            <strong>Match</strong> — a brand + model number + pack-size matcher with hard guards
            against bundle / refurbished / size-mismatch merges, falling back to RapidFuzz token
            sets and embedding cosine for rephrased titles.
          </li>
          <li>
            <strong>Embed + index</strong> — pluggable embedding provider (hashing default,
            sentence-transformers or OpenAI swap-in), vectors stored per-canonical-product.
          </li>
          <li>
            <strong>Search</strong> — keyword / semantic / hybrid modes. The query parser lifts{" "}
            <em>&ldquo;under 2000&rdquo;</em> out of the free text into a listing-level filter; the
            ranker blends cosine similarity, normalised discount, and rating.
          </li>
          <li>
            <strong>Cache + observe</strong> — pluggable cache (in-process LRU+TTL, Redis-ready)
            for hot queries; structured JSON logs and a Prometheus <code>/metrics</code>{" "}
            endpoint for latency, cache hit-rate, scrape outcomes, and breaker state.
          </li>
        </ol>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">Engineering choices worth flagging</h2>
        <ul className="list-disc space-y-2 pl-5 text-slate-700">
          <li>
            <strong>Filters apply at the listing level, not the product level.</strong> So{" "}
            <em>&ldquo;earbuds under ₹2000&rdquo;</em> still surfaces a product that&apos;s
            overpriced on Amazon if its Flipkart listing fits — the user gets one card with the
            cheap listing highlighted.
          </li>
          <li>
            <strong>Per-platform circuit breakers + retry with jitter.</strong> A Flipkart outage
            doesn&apos;t take Amazon and Nykaa down with it, and the breaker stops us from
            hammering a dead platform.
          </li>
          <li>
            <strong>CI ranking-quality gate.</strong> 15 hand-labeled queries with NDCG@5 and
            Precision@3 thresholds; merges fail if either headline metric regresses. The harness
            is hand-rolled (no scikit-learn just to compute three numbers).
          </li>
          <li>
            <strong>No vendor lock-in on observability.</strong> Logs are line-delimited JSON;{" "}
            <code>/metrics</code> is Prometheus text format. Drop in any backend without code
            changes.
          </li>
        </ul>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">What&apos;s real vs. demoed</h2>
        <p className="text-slate-700">
          The scrapers, matcher, embedding pipeline, search service, cache, scheduler, breakers,
          eval harness, and metrics endpoint are all production code with{" "}
          <strong>181 passing tests</strong>. The <em>live deploy</em> on this URL runs against a
          curated 120-product catalogue rather than scraping Amazon / Flipkart / Nykaa
          continuously, because all three forbid scraping in their ToS and would IP-ban the demo
          within hours. The scrapers in the repo are exercised against captured HTML fixtures so
          their parsing logic stays under test.
        </p>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">Stack</h2>
        <ul className="list-disc space-y-1 pl-5 text-slate-700">
          <li>
            <strong>Backend:</strong> FastAPI · SQLAlchemy · Pydantic v2 · APScheduler · RapidFuzz ·
            BeautifulSoup · Playwright · pytest
          </li>
          <li>
            <strong>Frontend:</strong> Next.js 14 (App Router) · React · TypeScript · Tailwind
          </li>
          <li>
            <strong>Data:</strong> PostgreSQL (Neon) · in-process JSON-vector index (pgvector
            swap-in documented)
          </li>
          <li>
            <strong>Deploy:</strong> Vercel (frontend) · Render (backend, Docker) · GitHub Actions CI
          </li>
        </ul>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">Read the code</h2>
        <p className="text-slate-700">
          The repo is organised by phase — each directory is a self-contained snapshot showing the
          system at that maturity level, so you can see the build-out without git-archaeology.{" "}
          <code>phase4/</code> is what runs here.
        </p>
      </section>
    </main>
  );
}
