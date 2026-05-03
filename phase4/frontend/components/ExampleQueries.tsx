"use client";

/**
 * Example query chips — recruiters won't type, they'll click. The set is
 * curated to show off the four interesting bits of the search pipeline:
 *
 *  - "noise cancelling headphones" → semantic synonym (XM5/XM4 don't say
 *    "noise cancelling" verbatim in every listing).
 *  - "good earbuds under 2000"     → query parser lifts ₹2000 into a
 *    listing-level filter.
 *  - "iphone 15"                   → grouping across 2+ platforms.
 *  - "vitamin c face wash"         → ingredient-aware semantic recall.
 *  - "moisturiser for dry skin"    → spelling + use-case stretch.
 */

const EXAMPLES = [
  "noise cancelling headphones",
  "good earbuds under 2000",
  "iphone 15",
  "vitamin c face wash",
  "moisturiser for dry skin",
  "wireless mouse",
];

type Props = {
  onPick: (query: string) => void;
};

export default function ExampleQueries({ onPick }: Props) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="text-xs uppercase tracking-wide text-slate-400">Try</span>
      {EXAMPLES.map((q) => (
        <button
          key={q}
          type="button"
          onClick={() => onPick(q)}
          className="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-700 ring-1 ring-slate-200 transition hover:bg-slate-900 hover:text-white"
        >
          {q}
        </button>
      ))}
    </div>
  );
}
