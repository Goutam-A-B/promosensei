"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Filters from "@/components/Filters";
import ModeToggle from "@/components/ModeToggle";
import QueryNotes from "@/components/QueryNotes";
import ResultsGrid from "@/components/ResultsGrid";
import SearchBar from "@/components/SearchBar";
import SkeletonGrid from "@/components/SkeletonGrid";
import { search, type SearchParams, type SearchResponse } from "@/lib/api";

export default function HomePage() {
  const [filters, setFilters] = useState<SearchParams>({
    q: "",
    mode: "semantic",
    sort: "relevance",
    page: 1
  });
  const [data, setData] = useState<SearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

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

  const showSimilarity =
    !!data && data.effective_mode !== "keyword" && (filters.q?.trim() ?? "") !== "";

  return (
    <main className="mx-auto flex min-h-screen max-w-6xl flex-col gap-6 px-4 py-8">
      <header className="flex flex-col gap-1">
        <h1 className="text-3xl font-bold tracking-tight">PromoSensei</h1>
        <p className="text-sm text-slate-500">
          Cross-platform offer discovery — Phase 2 (semantic search, Amazon catalog).
        </p>
      </header>

      <SearchBar initialQuery={filters.q ?? ""} onSubmit={onQuerySubmit} isLoading={loading} />

      <div className="flex flex-wrap items-center justify-between gap-3">
        <ModeToggle value={filters.mode ?? "semantic"} onChange={onModeChange} />
        <Filters filters={filters} onChange={onFiltersChange} />
      </div>

      {error && (
        <div role="alert" className="rounded-xl bg-red-50 p-4 text-sm text-red-700 ring-1 ring-red-200">
          Couldn't reach the API: {error}. Make sure the backend is running on{" "}
          <code className="rounded bg-red-100 px-1">localhost:8000</code>.
        </div>
      )}

      {loading && <SkeletonGrid />}

      {!loading && data && (
        <>
          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between text-sm text-slate-500">
              <span>{data.total.toLocaleString("en-IN")} deals</span>
              {data.query && <span>for &ldquo;{data.query}&rdquo;</span>}
            </div>
            <QueryNotes response={data} />
          </div>
          <ResultsGrid products={data.results} showSimilarity={showSimilarity} />
        </>
      )}
    </main>
  );
}
