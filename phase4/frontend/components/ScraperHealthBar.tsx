"use client";

import { useEffect, useState } from "react";
import { fetchScrapersHealth, type ScraperHealth } from "@/lib/api";

const PLATFORM_LABEL: Record<string, string> = {
  amazon: "Amazon",
  flipkart: "Flipkart",
  nykaa: "Nykaa"
};

export default function ScraperHealthBar() {
  const [data, setData] = useState<ScraperHealth[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    fetchScrapersHealth(controller.signal)
      .then((r) => setData(r.scrapers))
      .catch((err) => {
        if ((err as Error).name === "AbortError") return;
        setError((err as Error).message);
      });
    return () => controller.abort();
  }, []);

  if (error) {
    // Health bar is non-critical UI — fail silently rather than disrupt search.
    return null;
  }
  if (!data) return null;

  return (
    <div className="flex flex-wrap items-center gap-2 text-xs text-slate-600">
      <span className="text-slate-400">Catalog:</span>
      {data.map((s) => (
        <ScraperPill key={s.platform} health={s} />
      ))}
    </div>
  );
}

function ScraperPill({ health }: { health: ScraperHealth }) {
  const tone = pillTone(health);
  const label = PLATFORM_LABEL[health.platform] ?? health.platform;
  const tooltip = formatTooltip(health);
  return (
    <span
      title={tooltip}
      className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 ring-1 ${tone.bg} ${tone.ring} ${tone.text}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${tone.dot}`} />
      {label}
      <span className="text-slate-500">· {health.listings_count.toLocaleString("en-IN")}</span>
    </span>
  );
}

function pillTone(health: ScraperHealth) {
  if (health.last_status === null) {
    return { bg: "bg-slate-50", ring: "ring-slate-200", text: "text-slate-500", dot: "bg-slate-300" };
  }
  if (health.last_status === "ok" && health.success_rate_30d >= 0.8) {
    return { bg: "bg-emerald-50", ring: "ring-emerald-200", text: "text-emerald-700", dot: "bg-emerald-500" };
  }
  if (health.last_status === "failed") {
    return { bg: "bg-red-50", ring: "ring-red-200", text: "text-red-700", dot: "bg-red-500" };
  }
  return { bg: "bg-amber-50", ring: "ring-amber-200", text: "text-amber-700", dot: "bg-amber-500" };
}

function formatTooltip(h: ScraperHealth) {
  const parts: string[] = [];
  if (h.last_status) parts.push(`status: ${h.last_status}`);
  parts.push(`30d success: ${(h.success_rate_30d * 100).toFixed(0)}% (${h.runs_30d} runs)`);
  if (h.last_started_at) parts.push(`last run: ${new Date(h.last_started_at).toLocaleString()}`);
  if (h.last_error) parts.push(`last error: ${h.last_error}`);
  return parts.join("\n");
}
