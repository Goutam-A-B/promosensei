"use client";

// Material Design 3 ("Expressive · Dark") preview of PromoSensei.
//
// Self-contained: everything lives in this file. Deleting app/material/
// reverts to the default UI. Reuses lib/api.ts for data.
//
// Surface: deep aubergine-black with violet/fuchsia accent glows.
// Cards are translucent glass over the dark base. Brand colours read
// stronger on this canvas than they do on white.

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  search,
  fetchScrapersHealth,
  formatPrice,
  type GroupedProduct,
  type Listing,
  type ScraperHealth,
  type SearchParams,
  type SearchResponse,
} from "@/lib/api";

// ---------- constants ----------
const EXAMPLE_QUERIES = [
  "wireless earbuds under 2000",
  "skincare for oily skin",
  "running shoes mens",
  "smart tv 55 inch",
  "yoga mat thick",
  "mechanical keyboard",
];

const CATEGORIES: Array<{ key: string; label: string; emoji: string; query: string; tint: string }> = [
  { key: "audio",   label: "Audio",     emoji: "🎧", query: "wireless headphones",  tint: "from-indigo-500/30 to-indigo-500/20" },
  { key: "phones",  label: "Phones",    emoji: "📱", query: "smartphone under 30000", tint: "from-sky-500/30 to-blue-500/20" },
  { key: "laptops", label: "Laptops",   emoji: "💻", query: "laptop 16gb ram",      tint: "from-slate-400/20 to-zinc-500/20" },
  { key: "tv",      label: "TVs",       emoji: "📺", query: "smart tv 55 inch",     tint: "from-cyan-500/30 to-sky-500/20" },
  { key: "beauty",  label: "Beauty",    emoji: "💄", query: "lipstick matte",       tint: "from-pink-500/30 to-rose-500/20" },
  { key: "fashion", label: "Fashion",   emoji: "👟", query: "running shoes mens",   tint: "from-rose-500/30 to-sky-500/20" },
  { key: "home",    label: "Home",      emoji: "🏠", query: "air fryer",            tint: "from-emerald-500/30 to-teal-500/20" },
  { key: "fitness", label: "Fitness",   emoji: "🏋️", query: "yoga mat thick",       tint: "from-lime-500/30 to-emerald-500/20" },
];

const PLATFORM_LABEL: Record<string, string> = {
  amazon: "Amazon",
  flipkart: "Flipkart",
  nykaa: "Nykaa",
};

// Per-platform style atlas. Tailwind only sees literal strings, so every
// class needed for each platform is enumerated here.
const PLATFORM_ACCENT: Record<
  string,
  {
    chip: string;
    chipActive: string;
    dot: string;
    bar: string;            // gradient for the side stripe on rows
    rowHoverBg: string;     // gradient that tints the row on hover
    rowHoverRing: string;   // brand-tinted ring on hover
    rowHoverGlow: string;   // coloured shadow halo on hover
    cta: string;            // filled CTA button background
    ctaShadow: string;      // glow under CTA button
  }
> = {
  amazon: {
    chip: "border-orange-400/30 bg-orange-400/10 text-orange-200 hover:bg-orange-400/20",
    chipActive: "border-orange-400 bg-orange-500 text-white",
    dot: "bg-orange-400",
    bar: "from-orange-300 to-orange-500",
    rowHoverBg: "hover:bg-gradient-to-r hover:from-orange-500/25 hover:via-orange-500/5 hover:to-transparent",
    rowHoverRing: "hover:ring-orange-400/50",
    rowHoverGlow: "hover:shadow-[0_8px_24px_-12px_rgba(251,146,60,0.55)]",
    cta: "bg-orange-500 hover:bg-orange-400",
    ctaShadow: "shadow-orange-500/40",
  },
  flipkart: {
    chip: "border-blue-400/30 bg-blue-400/10 text-blue-200 hover:bg-blue-400/20",
    chipActive: "border-blue-400 bg-blue-500 text-white",
    dot: "bg-blue-400",
    bar: "from-blue-300 to-blue-500",
    rowHoverBg: "hover:bg-gradient-to-r hover:from-blue-500/25 hover:via-blue-500/5 hover:to-transparent",
    rowHoverRing: "hover:ring-blue-400/50",
    rowHoverGlow: "hover:shadow-[0_8px_24px_-12px_rgba(59,130,246,0.55)]",
    cta: "bg-blue-500 hover:bg-blue-400",
    ctaShadow: "shadow-blue-500/40",
  },
  nykaa: {
    chip: "border-pink-400/30 bg-pink-400/10 text-pink-200 hover:bg-pink-400/20",
    chipActive: "border-pink-400 bg-pink-500 text-white",
    dot: "bg-pink-400",
    bar: "from-pink-300 to-pink-500",
    rowHoverBg: "hover:bg-gradient-to-r hover:from-pink-500/25 hover:via-pink-500/5 hover:to-transparent",
    rowHoverRing: "hover:ring-pink-400/50",
    rowHoverGlow: "hover:shadow-[0_8px_24px_-12px_rgba(236,72,153,0.55)]",
    cta: "bg-pink-500 hover:bg-pink-400",
    ctaShadow: "shadow-pink-500/40",
  },
};

const PAGE_STYLES = `
  /* drifting mesh blobs in the hero */
  @keyframes meshDrift {
    0%   { transform: translate3d(0,0,0) scale(1); }
    33%  { transform: translate3d(3%,-2%,0) scale(1.06); }
    66%  { transform: translate3d(-3%,2%,0) scale(0.96); }
    100% { transform: translate3d(0,0,0) scale(1); }
  }
  .mesh-blob       { animation: meshDrift 18s ease-in-out infinite; }
  .mesh-blob-slow  { animation: meshDrift 26s ease-in-out infinite reverse; }

  /* shimmer for skeletons (dark-tuned) */
  @keyframes shimmer {
    0%   { background-position: -200% 0; }
    100% { background-position: 200% 0; }
  }
  .skeleton-shimmer {
    background: linear-gradient(90deg, rgba(255,255,255,0.04) 0%, rgba(255,255,255,0.10) 40%, rgba(255,255,255,0.04) 80%);
    background-size: 200% 100%;
    animation: shimmer 1.6s linear infinite;
  }

  /* discount badge pulse */
  @keyframes badgePulse {
    0%, 100% { box-shadow: 0 0 0 0 rgba(16,185,129,0.55); }
    50%      { box-shadow: 0 0 0 12px rgba(16,185,129,0); }
  }
  .badge-pulse { animation: badgePulse 2.4s ease-out infinite; }

  /* animated rotating gradient border for the featured card */
  @keyframes gradientPan {
    0%   { background-position: 0% 50%; }
    100% { background-position: 200% 50%; }
  }
  .border-gradient-pan {
    background: linear-gradient(115deg, #6366f1, #38bdf8, #f59e0b, #10b981, #6366f1);
    background-size: 200% 200%;
    animation: gradientPan 10s linear infinite;
  }

  /* sweeping shine across platform rows on hover */
  @keyframes rowShine {
    0%   { transform: translateX(-120%) skewX(-12deg); }
    100% { transform: translateX(220%) skewX(-12deg); }
  }
  .row-shine { animation: rowShine 1.1s ease-out; }

  /* dotted surface used behind product images */
  .dotted-surface {
    background-image: radial-gradient(circle at 1px 1px, rgba(255,255,255,0.07) 1px, transparent 0);
    background-size: 14px 14px;
  }

  /* very subtle grain overlay on the page background */
  .grain-overlay {
    background-image:
      radial-gradient(circle at 25% 20%, rgba(99,102,241,0.10), transparent 45%),
      radial-gradient(circle at 80% 0%, rgba(56,189,248,0.08), transparent 40%),
      radial-gradient(circle at 50% 100%, rgba(245,158,11,0.06), transparent 55%);
  }
  .grid-overlay {
    background-image:
      linear-gradient(rgba(255,255,255,0.025) 1px, transparent 1px),
      linear-gradient(90deg, rgba(255,255,255,0.025) 1px, transparent 1px);
    background-size: 48px 48px;
  }
`;

// ---------- page ----------
export default function MaterialHomePage() {
  const [filters, setFilters] = useState<SearchParams>({
    q: "",
    mode: "hybrid",
    sort: "relevance",
    page: 1,
  });
  const [data, setData] = useState<SearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const [showSticky, setShowSticky] = useState(false);
  const [showFab, setShowFab] = useState(false);
  const [saved, setSaved] = useState<Set<number>>(new Set());

  const runSearch = useCallback(async (params: SearchParams) => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setLoading(true);
    setError(null);
    try {
      const response = await search(params, controller.signal);
      setData(response);
    } catch (err) {
      if ((err as Error).name === "AbortError") return;
      setError((err as Error).message);
      setData(null);
    } finally {
      if (abortRef.current === controller) setLoading(false);
    }
  }, []);

  useEffect(() => {
    runSearch(filters);
    return () => abortRef.current?.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const onScroll = () => {
      const y = window.scrollY;
      setShowSticky(y > 320);
      setShowFab(y > 640);
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  const onQuerySubmit = (q: string) => {
    const next = { ...filters, q, page: 1 };
    setFilters(next);
    runSearch(next);
  };
  const onFiltersChange = (next: SearchParams) => {
    const reset = { ...next, page: 1 };
    setFilters(reset);
    runSearch(reset);
  };
  const onModeChange = (mode: NonNullable<SearchParams["mode"]>) => {
    const next = { ...filters, mode, page: 1 };
    setFilters(next);
    runSearch(next);
  };
  const toggleSave = (id: number) =>
    setSaved((prev) => {
      const n = new Set(prev);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });

  const showSimilarity =
    !!data && data.effective_mode !== "keyword" && (filters.q?.trim() ?? "") !== "";

  const hasQuery = (filters.q ?? "").trim().length > 0;
  const featured =
    !loading && data && data.results.length > 0 ? pickFeatured(data.results) : null;
  const restResults =
    featured && data ? data.results.filter((r) => r.id !== featured.id) : data?.results ?? [];

  return (
    <div className="relative min-h-screen text-slate-100">
      <style dangerouslySetInnerHTML={{ __html: PAGE_STYLES }} />

      {/* fixed dark canvas — moderate, not pitch */}
      <div className="fixed inset-0 -z-20 bg-[#161A22]" aria-hidden />
      <div className="fixed inset-0 -z-10 grain-overlay opacity-80" aria-hidden />
      <div className="pointer-events-none fixed inset-0 -z-10 grid-overlay opacity-40" aria-hidden />

      <TopAppBar />

      <StickyMiniBar
        visible={showSticky}
        total={data?.total ?? 0}
        query={filters.q ?? ""}
        loading={loading}
        onSubmit={onQuerySubmit}
      />

      <Hero
        query={filters.q ?? ""}
        loading={loading}
        onSubmit={onQuerySubmit}
      />

      <main className="relative z-10 mx-auto flex max-w-7xl flex-col gap-5 px-4 pb-20 pt-1 sm:px-6">
        {!hasQuery && (
          <div className="flex flex-wrap items-center gap-2">
            {CATEGORIES.slice(0, 6).map((c) => (
              <button
                key={c.key}
                type="button"
                onClick={() => onQuerySubmit(c.query)}
                className="inline-flex items-center gap-1.5 rounded-full border border-white/10 bg-white/[0.04] px-3 py-1 text-xs font-medium text-slate-200 transition hover:border-indigo-400/50 hover:bg-indigo-500/15 hover:text-white"
              >
                <span>{c.emoji}</span>
                {c.label}
              </button>
            ))}
          </div>
        )}

        <div className="flex flex-wrap gap-2">
          {EXAMPLE_QUERIES.map((q) => (
            <Chip key={q} onClick={() => onQuerySubmit(q)}>
              {q}
            </Chip>
          ))}
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3">
          <SegmentedModeToggle
            value={filters.mode ?? "hybrid"}
            onChange={onModeChange}
          />
          <FiltersBar filters={filters} onChange={onFiltersChange} />
        </div>
        <PlatformChipFilter
          value={filters.platform}
          onChange={(p) => onFiltersChange({ ...filters, platform: p })}
          onClear={() =>
            onFiltersChange({
              q: filters.q,
              mode: filters.mode,
              sort: "relevance",
              page: 1,
            })
          }
          anyActive={hasAnyFilter(filters)}
        />
        <ScraperHealthStrip />

        {error && (
          <div
            role="alert"
            className="rounded-3xl border border-rose-500/30 bg-rose-500/10 p-5 text-sm text-rose-100 backdrop-blur"
          >
            <strong className="font-semibold text-rose-200">Couldn&apos;t reach the API.</strong>{" "}
            {error}. The free-tier backend may be waking up — try again in ~30 seconds.
          </div>
        )}

        {loading && <SkeletonGrid />}

        {!loading && data && (
          <>
            <ResultsMeta
              total={data.total}
              query={data.query}
              latencyMs={data.latency_ms}
              cacheHit={data.cache_hit}
              effectiveMode={data.effective_mode}
              notes={data.notes}
            />

            {featured && (
              <FeaturedDeal
                product={featured}
                showSimilarity={showSimilarity}
                isSaved={saved.has(featured.id)}
                onToggleSave={() => toggleSave(featured.id)}
              />
            )}

            {restResults.length > 0 ? (
              <ResultsGrid
                products={restResults}
                showSimilarity={showSimilarity}
                saved={saved}
                onToggleSave={toggleSave}
              />
            ) : !featured ? (
              <EmptyState query={data.query} onPick={onQuerySubmit} />
            ) : null}
          </>
        )}

        <footer className="mt-6 border-t border-white/10 pt-6 text-xs text-slate-500">
          <p>
            Demo runs on a curated catalogue (~120 products). Production scrapers
            are real, tested code; the live deploy keeps them off to respect each
            platform&apos;s ToS.{" "}
            <Link
              href="/about"
              className="font-medium text-indigo-300 underline-offset-2 hover:underline"
            >
              Read more
            </Link>
            .
          </p>
        </footer>
      </main>

      {showFab && (
        <button
          type="button"
          onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
          aria-label="Back to top"
          className="fixed bottom-6 right-6 z-40 flex h-14 w-14 items-center justify-center rounded-2xl bg-indigo-600 text-white shadow-[0_0_30px_-5px_rgba(79,70,229,0.7)] ring-1 ring-indigo-400/40 transition hover:scale-105 hover:bg-indigo-500 active:scale-95"
        >
          <ArrowUpIcon className="h-6 w-6" />
        </button>
      )}
    </div>
  );
}

// ---------- helpers ----------
function hasAnyFilter(f: SearchParams) {
  return !!(
    f.platform ||
    f.min_price !== undefined ||
    f.max_price !== undefined ||
    f.min_rating !== undefined ||
    (f.sort && f.sort !== "relevance")
  );
}

function pickFeatured(results: GroupedProduct[]): GroupedProduct {
  const multi = results.find((r) => r.platform_count > 1);
  if (multi) return multi;
  const bigDeal = results.find((r) => {
    const d = r.listings[0]?.discount;
    return d ? Number(d) >= 30 : false;
  });
  return bigDeal ?? results[0];
}

function priceSpread(listings: Listing[]) {
  if (listings.length < 2) return null;
  const prices = listings.map((l) => Number(l.price));
  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const diff = max - min;
  return diff > 0 ? diff : null;
}

// ---------- top app bar ----------
function TopAppBar() {
  return (
    <div className="relative z-30 border-b border-white/10 bg-[#161A22]/75 backdrop-blur-xl">
      <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 py-3 sm:px-6">
        <Link href="/" className="flex items-center gap-2.5">
          <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-500 via-sky-500 to-amber-400 text-white shadow-[0_0_24px_-4px_rgba(99,102,241,0.7)]">
            <SparkleIcon className="h-5 w-5" />
          </div>
          <span className="text-base font-bold tracking-tight text-white">
            PromoSensei
          </span>
        </Link>
        <nav className="flex items-center gap-1.5 text-sm">
          <Link
            href="/about"
            className="rounded-full px-3 py-1.5 font-medium text-slate-300 transition hover:bg-white/10 hover:text-white"
          >
            How it works
          </Link>
        </nav>
      </div>
    </div>
  );
}

// ---------- sticky mini bar ----------
function StickyMiniBar({
  visible,
  total,
  query,
  loading,
  onSubmit,
}: {
  visible: boolean;
  total: number;
  query: string;
  loading: boolean;
  onSubmit: (q: string) => void;
}) {
  const [value, setValue] = useState(query);
  useEffect(() => setValue(query), [query]);
  return (
    <div
      className={
        "fixed inset-x-0 top-0 z-40 transition duration-300 " +
        (visible ? "translate-y-0 opacity-100" : "-translate-y-full opacity-0")
      }
      aria-hidden={!visible}
    >
      <div className="border-b border-white/10 bg-[#161A22]/85 backdrop-blur-xl">
        <div className="mx-auto flex max-w-7xl items-center gap-3 px-4 py-2.5 sm:px-6">
          <Link href="/" className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-sky-500 text-white shadow-[0_0_18px_-4px_rgba(99,102,241,0.7)]">
              <SparkleIcon className="h-4 w-4" />
            </div>
            <span className="hidden text-sm font-bold text-white sm:inline">
              PromoSensei
            </span>
          </Link>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              onSubmit(value.trim());
            }}
            className="flex flex-1 items-center gap-2 rounded-full border border-white/10 bg-white/5 px-4 py-1.5 focus-within:border-indigo-400/50 focus-within:bg-white/10"
          >
            <SearchIcon className="h-4 w-4 text-slate-400" />
            <input
              value={value}
              onChange={(e) => setValue(e.target.value)}
              placeholder="Search deals…"
              className="w-full bg-transparent text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none"
              aria-label="Search products"
            />
            {loading && <Spinner className="h-3.5 w-3.5 text-indigo-300" />}
          </form>
          {total > 0 && (
            <span className="hidden whitespace-nowrap rounded-full border border-indigo-400/30 bg-indigo-500/15 px-3 py-1 text-xs font-semibold text-indigo-200 sm:inline">
              {total.toLocaleString("en-IN")} deals
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

// ---------- Hero ----------
function Hero({
  query,
  loading,
  onSubmit,
}: {
  query: string;
  loading: boolean;
  onSubmit: (q: string) => void;
}) {
  const [value, setValue] = useState(query);
  useEffect(() => setValue(query), [query]);
  return (
    <header className="relative overflow-hidden">
      <div className="pointer-events-none absolute inset-0 -z-0 overflow-hidden">
        <div className="mesh-blob absolute -left-24 -top-10 h-80 w-80 rounded-full bg-indigo-500/20 blur-3xl" />
        <div className="mesh-blob-slow absolute -right-24 top-4 h-96 w-96 rounded-full bg-sky-500/20 blur-3xl" />
        <div className="mesh-blob absolute left-1/2 top-44 h-64 w-64 -translate-x-1/2 rounded-full bg-amber-400/15 blur-3xl" />
        <div className="mesh-blob-slow absolute left-1/3 top-0 h-56 w-56 rounded-full bg-emerald-400/12 blur-3xl" />
      </div>

      <div className="relative mx-auto flex max-w-7xl flex-col items-center gap-4 px-4 pb-8 pt-8 sm:px-6 sm:pt-12">
        <span className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/5 px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-indigo-200 backdrop-blur">
          <span className="relative flex h-1.5 w-1.5">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
            <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-emerald-400" />
          </span>
          Live · India · 3 platforms
        </span>

        <h1 className="text-balance text-center text-2xl font-bold tracking-tight text-white sm:text-3xl md:text-4xl">
          Find the deal{" "}
          <span className="bg-gradient-to-r from-indigo-300 via-sky-300 to-amber-200 bg-clip-text text-transparent">
            you actually meant.
          </span>
        </h1>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            onSubmit(value.trim());
          }}
          className="group flex w-full max-w-2xl items-center gap-2 rounded-full border border-white/10 bg-white/5 p-1.5 pl-4 shadow-[0_18px_50px_-20px_rgba(79,70,229,0.45)] backdrop-blur-xl transition focus-within:border-indigo-400/60 focus-within:bg-white/10"
        >
          <SearchIcon className="h-4 w-4 text-slate-400 transition group-focus-within:text-indigo-300" />
          <input
            type="text"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder='Try "wireless earbuds under 2000"'
            aria-label="Search products"
            className="w-full bg-transparent py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none sm:text-base"
          />
          {value && (
            <button
              type="button"
              onClick={() => {
                setValue("");
                onSubmit("");
              }}
              className="rounded-full p-1.5 text-slate-400 transition hover:bg-white/10 hover:text-white"
              aria-label="Clear search"
            >
              <XIcon className="h-4 w-4" />
            </button>
          )}
          <button
            type="submit"
            disabled={loading}
            className="flex items-center gap-2 rounded-full bg-indigo-500 px-5 py-2.5 text-sm font-semibold text-white shadow-[0_8px_24px_-6px_rgba(99,102,241,0.8)] transition hover:bg-indigo-400 disabled:cursor-not-allowed disabled:opacity-60 sm:px-6"
          >
            {loading ? (
              <>
                <Spinner /> Searching…
              </>
            ) : (
              <>
                Search
                <ArrowRightIcon className="h-4 w-4" />
              </>
            )}
          </button>
        </form>
      </div>
    </header>
  );
}

function SectionLabel({
  icon,
  children,
}: {
  icon?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.18em] text-indigo-300">
      <span className="text-indigo-400">{icon}</span>
      <span>{children}</span>
    </div>
  );
}

// ---------- Chip ----------
function Chip({
  children,
  onClick,
  selected,
  variant = "assist",
}: {
  children: React.ReactNode;
  onClick?: () => void;
  selected?: boolean;
  variant?: "assist" | "filter";
}) {
  const base =
    "inline-flex items-center gap-1.5 rounded-full border px-3.5 py-1.5 text-sm font-medium transition active:scale-95";
  const styles = selected
    ? "border-indigo-400 bg-indigo-500 text-white shadow-[0_0_16px_-4px_rgba(99,102,241,0.7)]"
    : "border-white/10 bg-white/5 text-slate-200 hover:border-indigo-400/50 hover:bg-indigo-500/15 hover:text-white";
  return (
    <button type="button" onClick={onClick} className={`${base} ${styles}`}>
      {variant === "filter" && selected && <CheckIcon className="h-3.5 w-3.5" />}
      {children}
    </button>
  );
}

// ---------- segmented mode toggle ----------
function SegmentedModeToggle({
  value,
  onChange,
}: {
  value: NonNullable<SearchParams["mode"]>;
  onChange: (v: NonNullable<SearchParams["mode"]>) => void;
}) {
  const opts: Array<{ v: NonNullable<SearchParams["mode"]>; label: string; hint: string }> = [
    { v: "keyword",  label: "Keyword",  hint: "Postgres full-text" },
    { v: "hybrid",   label: "Hybrid",   hint: "Keyword + vectors" },
    { v: "semantic", label: "Semantic", hint: "Pure embeddings" },
  ];
  return (
    <div className="inline-flex rounded-full border border-white/10 bg-white/5 p-1 backdrop-blur">
      {opts.map((o) => {
        const selected = value === o.v;
        return (
          <button
            key={o.v}
            type="button"
            onClick={() => onChange(o.v)}
            title={o.hint}
            className={
              "rounded-full px-4 py-1.5 text-sm font-medium transition " +
              (selected
                ? "bg-indigo-500 text-white shadow-[0_0_18px_-4px_rgba(99,102,241,0.8)]"
                : "text-slate-300 hover:bg-white/10 hover:text-white")
            }
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

// ---------- filters bar ----------
function FiltersBar({
  filters,
  onChange,
}: {
  filters: SearchParams;
  onChange: (next: SearchParams) => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-2 backdrop-blur">
      <FilterSelect
        label="Sort"
        value={filters.sort ?? "relevance"}
        onChange={(v) => onChange({ ...filters, sort: v as SearchParams["sort"] })}
        options={[
          { value: "relevance",     label: "Relevance" },
          { value: "price_asc",     label: "Price ↑" },
          { value: "price_desc",    label: "Price ↓" },
          { value: "discount_desc", label: "Biggest discount" },
          { value: "rating_desc",   label: "Highest rated" },
        ]}
      />
      <Divider />
      <NumField
        label="Min ₹"
        value={filters.min_price}
        onChange={(n) => onChange({ ...filters, min_price: n })}
      />
      <NumField
        label="Max ₹"
        value={filters.max_price}
        onChange={(n) => onChange({ ...filters, max_price: n })}
      />
      <NumField
        label="Min ★"
        value={filters.min_rating}
        max={5}
        step={0.5}
        onChange={(n) => onChange({ ...filters, min_rating: n })}
      />
    </div>
  );
}

function FilterSelect({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: Array<{ value: string; label: string }>;
}) {
  return (
    <label className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
      {label}
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-full border border-white/10 bg-[#1B1F28] px-3 py-1 text-sm font-medium normal-case tracking-normal text-slate-100 focus:border-indigo-400/60 focus:outline-none"
      >
        {options.map((o) => (
          <option key={o.value || "_all"} value={o.value} className="bg-[#1B1F28] text-slate-100">
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}

function NumField({
  label,
  value,
  onChange,
  max,
  step,
}: {
  label: string;
  value: number | undefined;
  onChange: (n: number | undefined) => void;
  max?: number;
  step?: number;
}) {
  return (
    <label className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
      {label}
      <input
        type="number"
        inputMode="decimal"
        min={0}
        max={max}
        step={step}
        value={value ?? ""}
        onChange={(e) =>
          onChange(e.target.value === "" ? undefined : Number(e.target.value))
        }
        className="w-20 rounded-full border border-white/10 bg-[#1B1F28] px-3 py-1 text-sm font-medium normal-case tracking-normal text-slate-100 placeholder:text-slate-500 focus:border-indigo-400/60 focus:outline-none"
      />
    </label>
  );
}

function Divider() {
  return <span className="hidden h-6 w-px bg-white/10 sm:inline-block" />;
}

// ---------- platform chip filter ----------
function PlatformChipFilter({
  value,
  onChange,
  onClear,
  anyActive,
}: {
  value: string | undefined;
  onChange: (p: string | undefined) => void;
  onClear: () => void;
  anyActive: boolean;
}) {
  const platforms = ["amazon", "flipkart", "nykaa"];
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="text-[11px] font-bold uppercase tracking-[0.18em] text-slate-400">
        Platform
      </span>
      <Chip variant="filter" selected={!value} onClick={() => onChange(undefined)}>
        All
      </Chip>
      {platforms.map((p) => {
        const accent = PLATFORM_ACCENT[p];
        const selected = value === p;
        return (
          <button
            key={p}
            type="button"
            onClick={() => onChange(selected ? undefined : p)}
            className={
              "inline-flex items-center gap-1.5 rounded-full border px-3.5 py-1.5 text-sm font-medium transition active:scale-95 " +
              (selected ? accent.chipActive : accent.chip)
            }
          >
            {selected && <CheckIcon className="h-3.5 w-3.5" />}
            <span className={`h-1.5 w-1.5 rounded-full ${selected ? "bg-white" : accent.dot}`} />
            {PLATFORM_LABEL[p]}
          </button>
        );
      })}
      {anyActive && (
        <button
          type="button"
          onClick={onClear}
          className="ml-1 inline-flex items-center gap-1 rounded-full px-3 py-1 text-xs font-semibold text-slate-400 hover:bg-white/10 hover:text-white"
        >
          <XIcon className="h-3.5 w-3.5" />
          Clear all
        </button>
      )}
    </div>
  );
}

// ---------- scraper health strip ----------
function ScraperHealthStrip() {
  const [scrapers, setScrapers] = useState<ScraperHealth[] | null>(null);
  useEffect(() => {
    const ctrl = new AbortController();
    fetchScrapersHealth(ctrl.signal)
      .then((r) => setScrapers(r.scrapers))
      .catch(() => setScrapers([]));
    return () => ctrl.abort();
  }, []);
  if (scrapers === null || scrapers.length === 0) return null;
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs text-slate-400">
      <span className="text-[11px] font-bold uppercase tracking-[0.18em] text-slate-500">
        Scraper health
      </span>
      {scrapers.map((s) => {
        const accent = PLATFORM_ACCENT[s.platform] ?? PLATFORM_ACCENT.amazon;
        const ok = s.success_rate_30d >= 0.9;
        return (
          <span
            key={s.platform}
            className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 ${accent.chip}`}
            title={`${s.runs_30d} runs in 30d — ${s.listings_count} listings`}
          >
            <span className={`h-1.5 w-1.5 rounded-full ${accent.dot}`} />
            {PLATFORM_LABEL[s.platform] ?? s.platform}
            <span className="font-mono text-[10px] opacity-70">
              {Math.round(s.success_rate_30d * 100)}%
            </span>
            <span aria-hidden>{ok ? "✓" : "!"}</span>
          </span>
        );
      })}
    </div>
  );
}

// ---------- results meta ----------
function ResultsMeta({
  total,
  query,
  latencyMs,
  cacheHit,
  effectiveMode,
  notes,
}: {
  total: number;
  query: string;
  latencyMs: number | null;
  cacheHit: boolean;
  effectiveMode: string;
  notes: string[];
}) {
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex items-baseline gap-3">
          <h2 className="text-lg font-bold tracking-tight text-white sm:text-xl">
            {total.toLocaleString("en-IN")}{" "}
            <span className="text-sm font-semibold text-slate-500">
              deal{total === 1 ? "" : "s"}
            </span>
          </h2>
          {query && (
            <span className="text-sm text-slate-500">
              for &ldquo;<span className="font-medium text-slate-200">{query}</span>&rdquo;
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <Pill tone="violet">{effectiveMode}</Pill>
          {latencyMs !== null && (
            <Pill tone={cacheHit ? "emerald" : "slate"}>
              <BoltIcon className="h-3 w-3" />
              {cacheHit ? "cache hit" : "fresh"} · {Math.round(latencyMs)} ms
            </Pill>
          )}
        </div>
      </div>
      {notes.length > 0 && (
        <ul className="flex flex-wrap gap-2 text-xs text-slate-400">
          {notes.map((n, i) => (
            <li
              key={i}
              className="rounded-full border border-amber-400/30 bg-amber-500/10 px-2.5 py-1 text-amber-200"
            >
              {n}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Pill({
  children,
  tone,
}: {
  children: React.ReactNode;
  tone: "violet" | "emerald" | "slate";
}) {
  const tones: Record<string, string> = {
    violet:  "border-indigo-400/30 bg-indigo-500/15 text-indigo-200",
    emerald: "border-emerald-400/30 bg-emerald-500/15 text-emerald-200",
    slate:   "border-white/10 bg-white/5 text-slate-300",
  };
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-semibold ${tones[tone]}`}
    >
      {children}
    </span>
  );
}

// ---------- featured deal ----------
function FeaturedDeal({
  product,
  showSimilarity,
  isSaved,
  onToggleSave,
}: {
  product: GroupedProduct;
  showSimilarity: boolean;
  isSaved: boolean;
  onToggleSave: () => void;
}) {
  const sortedListings = useMemo(
    () => [...product.listings].sort((a, b) => Number(a.price) - Number(b.price)),
    [product.listings]
  );
  const best = sortedListings[0];
  const worst = sortedListings[sortedListings.length - 1];
  const spread = priceSpread(product.listings);
  const bestDiscount = best?.discount ? Math.round(Number(best.discount)) : null;
  const similarityPct =
    showSimilarity && product.similarity > 0
      ? Math.round(product.similarity * 100)
      : null;
  const accent =
    best ? PLATFORM_ACCENT[best.platform] ?? PLATFORM_ACCENT.amazon : PLATFORM_ACCENT.amazon;

  return (
    <section className="relative overflow-hidden rounded-[28px] p-px shadow-[0_30px_80px_-30px_rgba(79,70,229,0.6)]">
      <div className="border-gradient-pan absolute inset-0 -z-0 rounded-[28px]" aria-hidden />
      <div className="relative grid grid-cols-1 gap-0 rounded-[27px] bg-[#100B1A] md:grid-cols-[minmax(0,1.05fr)_minmax(0,1fr)]">
        <div className="dotted-surface relative flex aspect-[4/3] items-center justify-center bg-gradient-to-br from-[#1A1230] to-[#0F0A1F] md:aspect-auto">
          {product.primary_image_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={product.primary_image_url}
              alt={product.canonical_title}
              loading="lazy"
              className="max-h-[70%] max-w-[70%] object-contain drop-shadow-[0_20px_40px_rgba(0,0,0,0.6)]"
            />
          ) : (
            <CategoryPlaceholder
              title={product.canonical_title}
              brand={product.brand}
              seed={product.id}
              big
            />
          )}

          <span className="absolute left-4 top-4 inline-flex items-center gap-1.5 rounded-full border border-indigo-400/40 bg-indigo-500/15 px-3 py-1.5 text-[11px] font-bold uppercase tracking-[0.16em] text-indigo-200 backdrop-blur">
            <SparkleIcon className="h-3 w-3" />
            Featured
          </span>
          {bestDiscount !== null && bestDiscount > 0 && (
            <span className="badge-pulse absolute right-4 top-4 inline-flex items-center rounded-full bg-emerald-500 px-3.5 py-1.5 text-sm font-bold text-white shadow-[0_0_30px_-5px_rgba(16,185,129,0.7)]">
              -{bestDiscount}% OFF
            </span>
          )}
          <button
            type="button"
            onClick={onToggleSave}
            aria-label={isSaved ? "Unsave" : "Save"}
            aria-pressed={isSaved}
            className={
              "absolute bottom-4 right-4 flex h-10 w-10 items-center justify-center rounded-full border backdrop-blur transition active:scale-90 " +
              (isSaved
                ? "border-rose-400 bg-rose-500 text-white shadow-[0_0_20px_-4px_rgba(244,63,94,0.7)]"
                : "border-white/15 bg-white/10 text-slate-200 hover:text-rose-300")
            }
          >
            <HeartIcon className="h-5 w-5" filled={isSaved} />
          </button>
        </div>

        <div className="flex flex-col gap-3 p-5 sm:p-6">
          <div className="flex flex-wrap items-center gap-2">
            {product.brand && (
              <span className="text-[10px] font-bold uppercase tracking-[0.16em] text-indigo-300">
                {product.brand}
              </span>
            )}
            {product.platform_count > 1 && (
              <Pill tone="slate">on {product.platform_count} platforms</Pill>
            )}
            {similarityPct !== null && (
              <Pill tone="violet">{similarityPct}% match</Pill>
            )}
          </div>
          <h3 className="text-lg font-bold leading-tight tracking-tight text-white sm:text-xl" dir="auto">
            {product.canonical_title}
          </h3>

          <div className="flex items-baseline gap-3">
            <span className="text-2xl font-extrabold tracking-tight text-white sm:text-3xl">
              {formatPrice(best?.price ?? null)}
            </span>
            {worst && worst.price !== best.price && (
              <span className="text-base text-slate-500 line-through">
                up to {formatPrice(worst.price)}
              </span>
            )}
          </div>

          {spread !== null && (
            <div className="inline-flex items-center gap-2 self-start rounded-full border border-emerald-400/30 bg-emerald-500/10 px-3 py-1.5 text-xs font-semibold text-emerald-200">
              <BoltIcon className="h-3.5 w-3.5" />
              Save up to {formatPrice(String(spread))} vs other platforms
            </div>
          )}

          <div className="mt-1 flex flex-col gap-2">
            {sortedListings.map((l, idx) => (
              <PlatformRow
                key={l.id}
                listing={l}
                isBest={idx === 0 && sortedListings.length > 1}
              />
            ))}
          </div>

          {best && (
            <a
              href={best.url}
              target="_blank"
              rel="noopener noreferrer nofollow"
              className={`mt-2 inline-flex items-center justify-center gap-2 self-start rounded-full px-6 py-3 text-sm font-bold text-white shadow-lg ${accent.cta} ${accent.ctaShadow} transition hover:shadow-xl active:scale-95`}
            >
              Open on {PLATFORM_LABEL[best.platform] ?? best.platform}
              <ArrowRightIcon className="h-4 w-4" />
            </a>
          )}
        </div>
      </div>
    </section>
  );
}

// ---------- results grid ----------
function ResultsGrid({
  products,
  showSimilarity,
  saved,
  onToggleSave,
}: {
  products: GroupedProduct[];
  showSimilarity?: boolean;
  saved: Set<number>;
  onToggleSave: (id: number) => void;
}) {
  return (
    <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
      {products.map((p) => (
        <MaterialProductCard
          key={p.id}
          product={p}
          showSimilarity={showSimilarity}
          isSaved={saved.has(p.id)}
          onToggleSave={() => onToggleSave(p.id)}
        />
      ))}
    </div>
  );
}

// ---------- empty state ----------
function EmptyState({
  query,
  onPick,
}: {
  query?: string;
  onPick: (q: string) => void;
}) {
  const trimmed = (query ?? "").trim();
  return (
    <div className="rounded-[28px] border border-white/10 bg-white/5 p-10 text-center backdrop-blur">
      <div className="mx-auto mb-5 flex h-20 w-20 items-center justify-center rounded-3xl bg-gradient-to-br from-indigo-500/40 via-sky-500/40 to-amber-400/40 text-4xl shadow-inner ring-1 ring-white/10">
        🔍
      </div>
      <h3 className="text-xl font-bold tracking-tight text-white">
        {trimmed ? <>Nothing matches &ldquo;{trimmed}&rdquo;</> : "No matching deals"}
      </h3>
      <p className="mx-auto mt-2 max-w-md text-sm text-slate-400">
        {trimmed
          ? "Our 120-product demo catalogue doesn't have this. Try a broader query, switch search mode, or pick a category below."
          : "Try a broader query or relax a filter."}
      </p>
      <div className="mx-auto mt-6 flex max-w-2xl flex-wrap justify-center gap-2">
        {CATEGORIES.slice(0, 6).map((c) => (
          <button
            key={c.key}
            type="button"
            onClick={() => onPick(c.query)}
            className="inline-flex items-center gap-2 rounded-full border border-indigo-400/30 bg-indigo-500/10 px-3.5 py-1.5 text-sm font-medium text-indigo-100 transition hover:border-indigo-400/60 hover:bg-indigo-500/20"
          >
            <span>{c.emoji}</span>
            {c.label}
          </button>
        ))}
      </div>
    </div>
  );
}

// ---------- product card ----------
function MaterialProductCard({
  product,
  showSimilarity,
  isSaved,
  onToggleSave,
}: {
  product: GroupedProduct;
  showSimilarity?: boolean;
  isSaved: boolean;
  onToggleSave: () => void;
}) {
  const sortedListings = useMemo(
    () => [...product.listings].sort((a, b) => Number(a.price) - Number(b.price)),
    [product.listings]
  );
  const best = sortedListings[0];
  const bestDiscount = best?.discount ? Math.round(Number(best.discount)) : null;
  const similarityPct =
    showSimilarity && product.similarity > 0
      ? Math.round(product.similarity * 100)
      : null;
  const spread = priceSpread(product.listings);
  const accent =
    best ? PLATFORM_ACCENT[best.platform] ?? PLATFORM_ACCENT.amazon : PLATFORM_ACCENT.amazon;
  const bigDeal = bestDiscount !== null && bestDiscount >= 40;

  return (
    <article
      className={
        "group relative flex flex-col overflow-hidden rounded-3xl border bg-white/[0.04] backdrop-blur-md transition duration-300 hover:-translate-y-1 " +
        (bigDeal
          ? "border-emerald-400/30 hover:border-emerald-400/60 hover:shadow-[0_24px_60px_-20px_rgba(16,185,129,0.55)]"
          : "border-white/10 hover:border-indigo-400/50 hover:shadow-[0_24px_60px_-20px_rgba(79,70,229,0.55)]")
      }
    >
      <div className="dotted-surface relative aspect-square w-full overflow-hidden bg-gradient-to-br from-[#1A1230] to-[#0F0A1F]">
        {product.primary_image_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={product.primary_image_url}
            alt={product.canonical_title}
            loading="lazy"
            className="h-full w-full object-contain p-4 transition duration-500 group-hover:scale-110"
          />
        ) : (
          <CategoryPlaceholder
            title={product.canonical_title}
            brand={product.brand}
            seed={product.id}
          />
        )}
        <div className="absolute inset-x-0 top-0 flex items-start justify-between gap-2 p-3">
          <div className="flex flex-col gap-1.5">
            {bestDiscount !== null && bestDiscount > 0 && (
              <span
                className={
                  "inline-flex items-center rounded-full px-2.5 py-1 text-xs font-bold text-white shadow-md " +
                  (bigDeal
                    ? "badge-pulse bg-gradient-to-r from-emerald-400 to-teal-500 shadow-[0_0_18px_-4px_rgba(16,185,129,0.8)]"
                    : "bg-gradient-to-r from-emerald-500 to-emerald-600")
                }
              >
                -{bestDiscount}%
              </span>
            )}
            {product.platform_count > 1 && (
              <span className="rounded-full border border-white/10 bg-black/60 px-2.5 py-1 text-[10px] font-semibold text-white backdrop-blur">
                {product.platform_count} platforms
              </span>
            )}
          </div>
          {similarityPct !== null && (
            <span
              title="Cosine similarity between your query and this product's embedding"
              className="rounded-full bg-indigo-500 px-2.5 py-1 text-xs font-bold text-white shadow-[0_0_14px_-2px_rgba(99,102,241,0.7)]"
            >
              {similarityPct}%
            </span>
          )}
        </div>

        <button
          type="button"
          onClick={onToggleSave}
          aria-label={isSaved ? "Unsave" : "Save"}
          aria-pressed={isSaved}
          className={
            "absolute bottom-3 right-3 flex h-9 w-9 items-center justify-center rounded-full border backdrop-blur transition active:scale-90 " +
            (isSaved
              ? "border-rose-400 bg-rose-500 text-white shadow-[0_0_16px_-2px_rgba(244,63,94,0.7)]"
              : "border-white/15 bg-black/40 text-slate-200 hover:text-rose-300")
          }
        >
          <HeartIcon className="h-4 w-4" filled={isSaved} />
        </button>
      </div>

      <div className="flex flex-1 flex-col gap-2.5 p-4">
        <div className="flex items-baseline justify-between gap-2">
          {product.brand ? (
            <span className="text-[10px] font-bold uppercase tracking-[0.16em] text-indigo-300">
              {product.brand}
            </span>
          ) : (
            <span />
          )}
          <span className="text-base font-extrabold tracking-tight text-white">
            {formatPrice(product.best_price)}
          </span>
        </div>

        <h3
          className="line-clamp-2 min-h-[2.5rem] text-sm font-semibold leading-snug text-slate-100"
          dir="auto"
        >
          {product.canonical_title}
        </h3>

        {spread !== null && (
          <div className="inline-flex items-center gap-1 self-start rounded-full border border-emerald-400/30 bg-emerald-500/10 px-2 py-0.5 text-[11px] font-semibold text-emerald-200">
            <BoltIcon className="h-3 w-3" />
            Save {formatPrice(String(spread))} elsewhere
          </div>
        )}

        <div className="mt-1 flex flex-col gap-1.5">
          {sortedListings.map((l, idx) => (
            <PlatformRow
              key={l.id}
              listing={l}
              isBest={idx === 0 && sortedListings.length > 1}
            />
          ))}
        </div>

        {best && (
          <a
            href={best.url}
            target="_blank"
            rel="noopener noreferrer nofollow"
            className={`mt-2 inline-flex items-center justify-center gap-1.5 rounded-full px-4 py-2 text-xs font-bold text-white shadow ${accent.cta} ${accent.ctaShadow} transition hover:shadow-lg active:scale-95`}
          >
            Open on {PLATFORM_LABEL[best.platform] ?? best.platform}
            <ArrowRightIcon className="h-3.5 w-3.5" />
          </a>
        )}
      </div>
    </article>
  );
}

// ---------- platform row (the part the user complained about) ----------
// Dark glass row, brand-tinted left bar that grows on hover, gradient
// hover-fill in the brand colour, soft coloured glow halo. The row stays
// dark-readable instead of fading to white.
function PlatformRow({ listing, isBest }: { listing: Listing; isBest: boolean }) {
  const accent = PLATFORM_ACCENT[listing.platform] ?? {
    chip: "",
    chipActive: "",
    dot: "bg-slate-400",
    bar: "from-slate-300 to-slate-500",
    rowHoverBg: "hover:bg-white/10",
    rowHoverRing: "hover:ring-white/20",
    rowHoverGlow: "",
    cta: "bg-slate-700 hover:bg-slate-600",
    ctaShadow: "shadow-slate-500/30",
  };
  const label = PLATFORM_LABEL[listing.platform] ?? listing.platform;
  return (
    <a
      href={listing.url}
      target="_blank"
      rel="noopener noreferrer nofollow"
      className={
        "group/link relative flex items-center justify-between gap-2 overflow-hidden rounded-2xl border border-white/10 bg-white/[0.03] px-3 py-2 text-sm ring-1 ring-transparent transition " +
        accent.rowHoverBg +
        " " +
        accent.rowHoverRing +
        " " +
        accent.rowHoverGlow
      }
    >
      {/* brand-coloured side bar — grows on hover */}
      <span
        className={`absolute inset-y-0 left-0 w-1 bg-gradient-to-b ${accent.bar} transition-all duration-300 group-hover/link:w-1.5`}
        aria-hidden
      />
      {/* sweeping shine */}
      <span
        className="pointer-events-none absolute inset-y-0 -left-1/2 w-1/3 -skew-x-12 bg-gradient-to-r from-transparent via-white/10 to-transparent opacity-0 transition-opacity duration-300 group-hover/link:opacity-100 group-hover/link:row-shine"
        aria-hidden
      />
      <span className="relative z-10 flex items-center gap-2 pl-2">
        <span className={`h-2 w-2 rounded-full ${accent.dot}`} aria-hidden />
        <span className="font-semibold text-slate-100">{label}</span>
        {isBest && (
          <span className="rounded-full bg-emerald-500 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-white">
            best
          </span>
        )}
        {listing.rating && (
          <span className="text-xs font-semibold text-amber-300">
            ★ {Number(listing.rating).toFixed(1)}
          </span>
        )}
      </span>
      <span className="relative z-10 flex items-center gap-1.5">
        <span className="font-bold text-white">{formatPrice(listing.price)}</span>
        <span className="text-indigo-300 transition group-hover/link:translate-x-0.5 group-hover/link:text-white">
          →
        </span>
      </span>
    </a>
  );
}

// ---------- skeleton ----------
function SkeletonGrid() {
  return (
    <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
      {Array.from({ length: 8 }).map((_, i) => (
        <div
          key={i}
          className="overflow-hidden rounded-3xl border border-white/10 bg-white/[0.04] backdrop-blur"
        >
          <div className="skeleton-shimmer aspect-square w-full" />
          <div className="space-y-2 p-4">
            <div className="skeleton-shimmer h-3 w-1/3 rounded-full" />
            <div className="skeleton-shimmer h-4 w-5/6 rounded-full" />
            <div className="skeleton-shimmer h-4 w-3/4 rounded-full" />
            <div className="skeleton-shimmer mt-3 h-9 w-full rounded-2xl" />
            <div className="skeleton-shimmer h-9 w-full rounded-2xl" />
          </div>
        </div>
      ))}
    </div>
  );
}

// ---------- category placeholder ----------
const CATEGORY_RULES: Array<{ pattern: RegExp; emoji: string; gradient: string }> = [
  { pattern: /headphone|headset|earbud|airpod|airdopes|buds|speaker/i, emoji: "🎧", gradient: "bg-gradient-to-br from-indigo-700/60 to-indigo-700/60" },
  { pattern: /iphone|galaxy s|pixel|oneplus|redmi|vivo|oppo|realme|smartphone|mobile|nothing phone/i, emoji: "📱", gradient: "bg-gradient-to-br from-sky-700/60 to-blue-700/60" },
  { pattern: /ipad|galaxy tab|tablet/i, emoji: "📱", gradient: "bg-gradient-to-br from-indigo-700/60 to-blue-700/60" },
  { pattern: /laptop|macbook|ideapad|inspiron|pavilion|notebook|chromebook/i, emoji: "💻", gradient: "bg-gradient-to-br from-slate-700/60 to-zinc-700/60" },
  { pattern: /keyboard|mouse|webcam|monitor|printer/i, emoji: "⌨️", gradient: "bg-gradient-to-br from-stone-700/60 to-stone-800/60" },
  { pattern: /watch|smartwatch|band|fitness tracker/i, emoji: "⌚", gradient: "bg-gradient-to-br from-amber-700/60 to-orange-700/60" },
  { pattern: /air fryer|microwave|refrigerator|washing machine|vacuum|robot vacuum|kettle|toaster|blender|mixer|grinder|oven/i, emoji: "🏠", gradient: "bg-gradient-to-br from-teal-700/60 to-emerald-700/60" },
  { pattern: /\btv\b|television|smart tv|qled|oled\b/i, emoji: "📺", gradient: "bg-gradient-to-br from-cyan-700/60 to-sky-700/60" },
  { pattern: /playstation|ps5|xbox|nintendo|gaming|controller/i, emoji: "🎮", gradient: "bg-gradient-to-br from-sky-700/60 to-pink-700/60" },
  { pattern: /camera|gopro|dslr|mirrorless|lens/i, emoji: "📷", gradient: "bg-gradient-to-br from-zinc-700/60 to-slate-700/60" },
  { pattern: /book|hardcover|paperback|\bby [A-Z]/, emoji: "📚", gradient: "bg-gradient-to-br from-orange-700/60 to-rose-700/60" },
  { pattern: /shoe|sneaker|sandal|loafer|boot|footwear/i, emoji: "👟", gradient: "bg-gradient-to-br from-lime-700/60 to-green-700/60" },
  { pattern: /yoga|dumbbell|gym|cricket|football|shuttle|racquet|fitness band|exercise/i, emoji: "🏋️", gradient: "bg-gradient-to-br from-emerald-700/60 to-teal-700/60" },
  { pattern: /cleanser|moisturi[sz]|serum|toner|sunscreen|face wash|cream|spf/i, emoji: "🧴", gradient: "bg-gradient-to-br from-emerald-700/60 to-cyan-700/60" },
  { pattern: /lipstick|foundation|kajal|eyeliner|mascara|blush|primer|nail polish/i, emoji: "💄", gradient: "bg-gradient-to-br from-pink-700/60 to-rose-700/60" },
  { pattern: /shampoo|conditioner|hair oil|hair dryer|hair colour|hair color/i, emoji: "💇", gradient: "bg-gradient-to-br from-amber-700/60 to-yellow-700/60" },
  { pattern: /perfume|fragrance|cologne|eau de|deodorant/i, emoji: "🌸", gradient: "bg-gradient-to-br from-rose-700/60 to-sky-700/60" },
  { pattern: /t-shirt|tshirt|shirt|jeans|trouser|kurta|saree|dress\b|hoodie|jacket|sweater|kurti|leggings|polo|innerwear|shorts/i, emoji: "👕", gradient: "bg-gradient-to-br from-rose-700/60 to-pink-700/60" },
  { pattern: /backpack|handbag|wallet|luggage|trolley|duffle/i, emoji: "🎒", gradient: "bg-gradient-to-br from-amber-700/60 to-orange-700/60" },
  { pattern: /pen\b|notebook|stationery|diary/i, emoji: "✒️", gradient: "bg-gradient-to-br from-stone-700/60 to-amber-700/60" },
  { pattern: /drone|quadcopter/i, emoji: "🚁", gradient: "bg-gradient-to-br from-sky-700/60 to-cyan-700/60" },
];
const FALLBACK_GRADIENTS = [
  "bg-gradient-to-br from-rose-700/50 to-rose-900/50",
  "bg-gradient-to-br from-amber-700/50 to-amber-900/50",
  "bg-gradient-to-br from-emerald-700/50 to-emerald-900/50",
  "bg-gradient-to-br from-sky-700/50 to-sky-900/50",
  "bg-gradient-to-br from-indigo-700/50 to-indigo-900/50",
  "bg-gradient-to-br from-sky-700/50 to-sky-900/50",
  "bg-gradient-to-br from-teal-700/50 to-teal-900/50",
  "bg-gradient-to-br from-orange-700/50 to-orange-900/50",
];
function classifyCategory(title: string) {
  for (const rule of CATEGORY_RULES) {
    if (rule.pattern.test(title)) return { emoji: rule.emoji, gradient: rule.gradient };
  }
  return { emoji: "🛍️", gradient: "" };
}
function CategoryPlaceholder({
  title,
  brand,
  seed,
  big,
}: {
  title: string;
  brand: string | null;
  seed: number;
  big?: boolean;
}) {
  const { emoji, gradient } = classifyCategory(title);
  const finalGradient = gradient || FALLBACK_GRADIENTS[seed % FALLBACK_GRADIENTS.length];
  return (
    <div className={`relative flex h-full w-full flex-col items-center justify-center ${finalGradient}`}>
      <div className={`drop-shadow-lg transition-transform duration-300 group-hover:scale-110 ${big ? "text-9xl" : "text-7xl"}`}>
        {emoji}
      </div>
      {brand && (
        <div className="mt-4 rounded-full border border-white/15 bg-black/40 px-3 py-1 text-[11px] font-bold uppercase tracking-[0.16em] text-slate-100 backdrop-blur">
          {brand}
        </div>
      )}
    </div>
  );
}

// ---------- icons ----------
function SearchIcon({ className = "h-5 w-5" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden>
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-3.5-3.5" />
    </svg>
  );
}
function SparkleIcon({ className = "h-5 w-5" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" className={className} aria-hidden>
      <path d="M12 2 14 9l7 2-7 2-2 7-2-7-7-2 7-2 2-7Z" />
    </svg>
  );
}
function ArrowUpIcon({ className = "h-5 w-5" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden>
      <path d="M12 19V5" />
      <path d="m5 12 7-7 7 7" />
    </svg>
  );
}
function ArrowRightIcon({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden>
      <path d="M5 12h14" />
      <path d="m13 5 7 7-7 7" />
    </svg>
  );
}
function CheckIcon({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden>
      <path d="m5 12 5 5L20 7" />
    </svg>
  );
}
function XIcon({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden>
      <path d="M6 6l12 12" />
      <path d="M6 18 18 6" />
    </svg>
  );
}
function HeartIcon({ className = "h-5 w-5", filled }: { className?: string; filled?: boolean }) {
  return (
    <svg viewBox="0 0 24 24" fill={filled ? "currentColor" : "none"} stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden>
      <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 1 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78Z" />
    </svg>
  );
}
function GridIcon({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden>
      <rect x="3" y="3" width="7" height="7" rx="1.5" />
      <rect x="14" y="3" width="7" height="7" rx="1.5" />
      <rect x="3" y="14" width="7" height="7" rx="1.5" />
      <rect x="14" y="14" width="7" height="7" rx="1.5" />
    </svg>
  );
}
function BoltIcon({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" className={className} aria-hidden>
      <path d="M13 2 4 14h7l-1 8 9-12h-7l1-8Z" />
    </svg>
  );
}
function Spinner({ className = "h-4 w-4 text-white" }: { className?: string }) {
  return (
    <svg className={`${className} animate-spin`} viewBox="0 0 24 24" fill="none" aria-hidden>
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeOpacity="0.25" strokeWidth="3" />
      <path d="M21 12a9 9 0 0 1-9 9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}
