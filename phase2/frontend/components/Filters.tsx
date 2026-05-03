"use client";

import type { SearchParams } from "@/lib/api";

type Props = {
  filters: SearchParams;
  onChange: (next: SearchParams) => void;
};

const SORTS: Array<{ value: NonNullable<SearchParams["sort"]>; label: string }> = [
  { value: "relevance", label: "Relevance" },
  { value: "price_asc", label: "Price: Low → High" },
  { value: "price_desc", label: "Price: High → Low" },
  { value: "discount_desc", label: "Biggest discount" },
  { value: "rating_desc", label: "Highest rated" }
];

export default function Filters({ filters, onChange }: Props) {
  return (
    <div className="flex flex-wrap items-center gap-3 rounded-xl bg-white p-3 ring-1 ring-slate-200">
      <label className="flex items-center gap-2 text-sm text-slate-700">
        Sort
        <select
          value={filters.sort ?? "relevance"}
          onChange={(e) => onChange({ ...filters, sort: e.target.value as SearchParams["sort"] })}
          className="rounded-md border border-slate-300 bg-white px-2 py-1 text-sm focus:border-accent focus:outline-none"
        >
          {SORTS.map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
            </option>
          ))}
        </select>
      </label>

      <label className="flex items-center gap-2 text-sm text-slate-700">
        Min ₹
        <input
          type="number"
          inputMode="numeric"
          min={0}
          value={filters.min_price ?? ""}
          onChange={(e) =>
            onChange({ ...filters, min_price: e.target.value === "" ? undefined : Number(e.target.value) })
          }
          className="w-24 rounded-md border border-slate-300 px-2 py-1 text-sm"
        />
      </label>

      <label className="flex items-center gap-2 text-sm text-slate-700">
        Max ₹
        <input
          type="number"
          inputMode="numeric"
          min={0}
          value={filters.max_price ?? ""}
          onChange={(e) =>
            onChange({ ...filters, max_price: e.target.value === "" ? undefined : Number(e.target.value) })
          }
          className="w-24 rounded-md border border-slate-300 px-2 py-1 text-sm"
        />
      </label>

      <label className="flex items-center gap-2 text-sm text-slate-700">
        Min ★
        <input
          type="number"
          inputMode="decimal"
          min={0}
          max={5}
          step={0.5}
          value={filters.min_rating ?? ""}
          onChange={(e) =>
            onChange({ ...filters, min_rating: e.target.value === "" ? undefined : Number(e.target.value) })
          }
          className="w-20 rounded-md border border-slate-300 px-2 py-1 text-sm"
        />
      </label>
    </div>
  );
}
