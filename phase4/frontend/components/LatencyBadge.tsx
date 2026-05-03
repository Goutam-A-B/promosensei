import type { SearchResponse } from "@/lib/api";

type Props = {
  response: Pick<SearchResponse, "cache_hit" | "latency_ms">;
};

/**
 * Phase 4 — small "cached · 3 ms" or "fresh · 412 ms" badge next to the
 * results count. Helps the demo make the cache visible (architecture.md
 * Phase 4 cache TTL is 5 min) and gives a quick sniff of latency without
 * opening devtools.
 */
export default function LatencyBadge({ response }: Props) {
  const { cache_hit, latency_ms } = response;
  if (latency_ms === null || latency_ms === undefined) return null;

  const rounded = Math.round(latency_ms);
  const label = cache_hit ? "cached" : "fresh";
  const tone = cache_hit
    ? "bg-emerald-50 text-emerald-700 ring-emerald-200"
    : "bg-slate-50 text-slate-600 ring-slate-200";

  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs ring-1 ${tone}`}
      title={cache_hit ? "Served from the in-process cache (5 min TTL)" : "Computed from scratch"}
    >
      <span className="font-medium">{label}</span>
      <span aria-hidden>·</span>
      <span>{rounded} ms</span>
    </span>
  );
}
