import type { SearchResponse } from "@/lib/api";

/**
 * Surfaces the parser's view of a query so users can see why their results
 * came back the way they did. For example, "earbuds under 2000" shows:
 *   - intent: earbuds
 *   - max_price=2000
 *   - mode: semantic (asked) → keyword (effective, if index was empty)
 */
export default function QueryNotes({ response }: { response: SearchResponse }) {
  const { parsed_residual, query, mode, effective_mode, notes } = response;

  const showFallback = mode !== effective_mode;
  const cleanResidual = parsed_residual && parsed_residual !== query;

  if (!showFallback && !cleanResidual && notes.length === 0) return null;

  return (
    <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
      {cleanResidual && (
        <span className="rounded-full bg-slate-100 px-2 py-0.5">
          intent: <span className="font-medium text-ink">{parsed_residual}</span>
        </span>
      )}
      {notes.map((note, i) => (
        <span
          key={i}
          className="rounded-full bg-blue-50 px-2 py-0.5 text-blue-700 ring-1 ring-blue-100"
        >
          {note}
        </span>
      ))}
      {showFallback && (
        <span className="rounded-full bg-amber-50 px-2 py-0.5 text-amber-700 ring-1 ring-amber-100">
          {mode} → {effective_mode}
        </span>
      )}
    </div>
  );
}
