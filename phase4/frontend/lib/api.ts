const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export type Listing = {
  id: number;
  platform: string;
  platform_product_id: string;
  price: string;
  original_price: string | null;
  discount: string | null;
  rating: string | null;
  url: string;
  image_url: string | null;
  last_seen_at: string;
};

export type GroupedProduct = {
  id: number;
  canonical_title: string;
  brand: string | null;
  model_number: string | null;
  category: string | null;
  primary_image_url: string | null;
  best_price: string;
  best_platform: string;
  platform_count: number;
  listings: Listing[];
  score: number;
  similarity: number;
};

export type SearchMode = "keyword" | "semantic" | "hybrid";

export type SearchResponse = {
  query: string;
  parsed_residual: string;
  mode: SearchMode;
  effective_mode: SearchMode;
  notes: string[];
  total: number;
  page: number;
  page_size: number;
  results: GroupedProduct[];
  /** Phase 4: true when the API served from its hot-query cache. */
  cache_hit: boolean;
  /** Phase 4: server-measured latency including the cache check. */
  latency_ms: number | null;
};

export type SearchParams = {
  q?: string;
  mode?: SearchMode;
  min_price?: number;
  max_price?: number;
  min_rating?: number;
  platform?: string;
  sort?: "relevance" | "price_asc" | "price_desc" | "discount_desc" | "rating_desc";
  page?: number;
  page_size?: number;
};

export type ScraperHealth = {
  platform: string;
  last_started_at: string | null;
  last_finished_at: string | null;
  last_status: string | null;
  success_rate_30d: number;
  runs_30d: number;
  listings_count: number;
  last_error: string | null;
};

export type ScrapersHealthResponse = {
  scrapers: ScraperHealth[];
};

export async function search(params: SearchParams, signal?: AbortSignal): Promise<SearchResponse> {
  const url = new URL(`${API_BASE}/search`);
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "") continue;
    url.searchParams.set(k, String(v));
  }

  const res = await fetch(url.toString(), { signal, cache: "no-store" });
  if (!res.ok) {
    throw new Error(`Search failed: ${res.status} ${res.statusText}`);
  }
  return (await res.json()) as SearchResponse;
}

export async function fetchScrapersHealth(signal?: AbortSignal): Promise<ScrapersHealthResponse> {
  const res = await fetch(`${API_BASE}/health/scrapers`, { signal, cache: "no-store" });
  if (!res.ok) {
    throw new Error(`Health check failed: ${res.status} ${res.statusText}`);
  }
  return (await res.json()) as ScrapersHealthResponse;
}

export function formatPrice(value: string | null): string {
  if (value === null || value === undefined) return "—";
  const n = Number(value);
  if (Number.isNaN(n)) return value;
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0
  }).format(n);
}
