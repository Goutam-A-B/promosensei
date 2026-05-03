const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export type Product = {
  id: number;
  platform: string;
  platform_product_id: string;
  title: string;
  price: string;
  original_price: string | null;
  discount: string | null;
  rating: string | null;
  url: string;
  image_url: string | null;
  updated_at: string;
};

export type SearchHit = Product & {
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
  results: SearchHit[];
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
