import type { Product } from "@/lib/api";
import { formatPrice } from "@/lib/api";

export default function ProductCard({ product }: { product: Product }) {
  const discount = product.discount ? Math.round(Number(product.discount)) : null;

  return (
    <a
      href={product.url}
      target="_blank"
      rel="noopener noreferrer nofollow"
      className="group flex flex-col overflow-hidden rounded-2xl bg-white shadow-sm ring-1 ring-slate-200 transition hover:-translate-y-0.5 hover:shadow-md"
    >
      <div className="relative aspect-square w-full overflow-hidden bg-slate-100">
        {product.image_url ? (
          // Plain <img> avoids next/image domain config friction in Phase 1.
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={product.image_url}
            alt={product.title}
            className="h-full w-full object-contain p-3 transition group-hover:scale-105"
            loading="lazy"
          />
        ) : (
          <div className="flex h-full items-center justify-center text-xs text-slate-400">
            No image
          </div>
        )}
        {discount !== null && discount > 0 && (
          <span className="absolute left-2 top-2 rounded-full bg-emerald-600 px-2 py-0.5 text-xs font-semibold text-white">
            {discount}% off
          </span>
        )}
      </div>

      <div className="flex flex-1 flex-col gap-2 p-3">
        <h3 className="line-clamp-2 text-sm font-medium text-ink" dir="auto">
          {product.title}
        </h3>

        <div className="mt-auto flex items-baseline gap-2">
          <span className="text-base font-semibold">{formatPrice(product.price)}</span>
          {product.original_price && (
            <span className="text-xs text-slate-400 line-through">
              {formatPrice(product.original_price)}
            </span>
          )}
        </div>

        <div className="flex items-center justify-between text-xs text-slate-500">
          <span className="rounded-full bg-slate-100 px-2 py-0.5 capitalize">{product.platform}</span>
          {product.rating && <span>★ {Number(product.rating).toFixed(1)}</span>}
        </div>
      </div>
    </a>
  );
}
