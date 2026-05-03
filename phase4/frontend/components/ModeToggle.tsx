"use client";

import type { SearchMode } from "@/lib/api";

type Props = {
  value: SearchMode;
  onChange: (mode: SearchMode) => void;
};

const MODES: Array<{ value: SearchMode; label: string; hint: string }> = [
  { value: "semantic", label: "Semantic", hint: "Intent-aware ranking" },
  { value: "hybrid", label: "Hybrid", hint: "Semantic + exact-match fallback" },
  { value: "keyword", label: "Keyword", hint: "Phase 1 token match" }
];

export default function ModeToggle({ value, onChange }: Props) {
  return (
    <div
      role="radiogroup"
      aria-label="Search mode"
      className="inline-flex rounded-xl bg-slate-100 p-1 ring-1 ring-slate-200"
    >
      {MODES.map((m) => {
        const active = value === m.value;
        return (
          <button
            key={m.value}
            role="radio"
            aria-checked={active}
            title={m.hint}
            onClick={() => onChange(m.value)}
            className={
              "rounded-lg px-3 py-1 text-sm font-medium transition " +
              (active
                ? "bg-white text-ink shadow-sm ring-1 ring-slate-200"
                : "text-slate-500 hover:text-ink")
            }
          >
            {m.label}
          </button>
        );
      })}
    </div>
  );
}
