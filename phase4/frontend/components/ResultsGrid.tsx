import type { GroupedProduct } from "@/lib/api";
import ProductCard from "./ProductCard";

type Props = {
  products: GroupedProduct[];
  showSimilarity?: boolean;
};

export default function ResultsGrid({ products, showSimilarity = false }: Props) {
  if (products.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-slate-300 bg-white p-10 text-center text-slate-500">
        No matching deals. Try a broader query or relax a filter.
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
