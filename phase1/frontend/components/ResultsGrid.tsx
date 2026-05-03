import type { Product } from "@/lib/api";
import ProductCard from "./ProductCard";

export default function ResultsGrid({ products }: { products: Product[] }) {
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
        <ProductCard key={`${p.platform}-${p.platform_product_id}`} product={p} />
      ))}
    </div>
  );
}
