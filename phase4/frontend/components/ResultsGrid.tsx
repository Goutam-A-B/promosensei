import type { GroupedProduct } from "@/lib/api";
import ProductCard from "./ProductCard";

type Props = {
  products: GroupedProduct[];
  showSimilarity?: boolean;
  query?: string;
};

export default function ResultsGrid({ products, showSimilarity = false, query }: Props) {
  if (products.length === 0) {
    const trimmed = (query ?? "").trim();
    return (
      <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-12 text-center">
        <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-slate-100 text-3xl">
          🔍
        </div>
        <h3 className="text-base font-semibold text-slate-900">
          {trimmed ? <>Nothing matches &ldquo;{trimmed}&rdquo;</> : "No matching deals"}
        </h3>
        <p className="mx-auto mt-2 max-w-md text-sm text-slate-500">
          {trimmed
            ? "Our 120-product demo catalogue doesn't have this. Try a broader query, switch search mode, or pick one of the example chips above."
            : "Try a broader query or relax a filter."}
        </p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
      {products.map((p) => (
        <ProductCard key={p.id} product={p} showSimilarity={showSimilarity} />
      ))}
    </div>
  );
}
