import type { GroupedProduct, Listing } from "@/lib/api";
import { formatPrice } from "@/lib/api";

type Props = {
  product: GroupedProduct;
  showSimilarity?: boolean;
};

const PLATFORM_LABEL: Record<string, string> = {
  amazon: "Amazon",
  flipkart: "Flipkart",
  nykaa: "Nykaa"
};

export default function ProductCard({ product, showSimilarity = false }: Props) {
  const best = product.listings.find((l) => l.platform === product.best_platform) ?? product.listings[0];
  const bestDiscount = best?.discount ? Math.round(Number(best.discount)) : null;
  const similarityPct =
    showSimilarity && product.similarity > 0 ? Math.round(product.similarity * 100) : null;

  const otherListings = product.listings.filter((l) => l !== best);

  return (
    <article className="group flex flex-col overflow-hidden rounded-2xl bg-white shadow-sm ring-1 ring-slate-200 transition hover:-translate-y-0.5 hover:shadow-md">
      <a
        href={best?.url}
        target="_blank"
        rel="noopener noreferrer nofollow"
        className="relative block aspect-square w-full overflow-hidden bg-slate-100"
      >
        {product.primary_image_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={product.primary_image_url}
            alt={product.canonical_title}
            className="h-full w-full object-contain p-3 transition group-hover:scale-105"
            loading="lazy"
          />
        ) : (
          <div className="flex h-full items-center justify-center text-xs text-slate-400">No image</div>
        )}
        {bestDiscount !== null && bestDiscount > 0 && (
          <span className="absolute left-2 top-2 rounded-full bg-emerald-600 px-2 py-0.5 text-xs font-semibold text-white">
            {bestDiscount}% off
          </span>
        )}
        {product.platform_count > 1 && (
          <span className="absolute right-2 top-2 rounded-full bg-slate-900/85 px-2 py-0.5 text-xs font-semibold text-white">
            {product.platform_count} platforms
          </span>
        )}
      </a>

      <div className="flex flex-1 flex-col gap-2 p-3">
        <div className="flex items-baseline justify-between gap-2">
          {product.brand && (
            <span className="text-xs uppercase tracking-wide text-slate-500">{product.brand}</span>
          )}
          {similarityPct !== null && (
            <span
              title="Cosine similarity between your query and this product's embedding"
              className="rounded-full bg-blue-50 px-2 py-0.5 text-xs text-blue-700 ring-1 ring-blue-100"
            >
              {similarityPct}% match
            </span>
          )}
        </div>

        <h3 className="line-clamp-2 text-sm font-medium text-ink" dir="auto">
          {product.canonical_title}
        </h3>

        <div className="flex items-baseline gap-2">
          <span className="text-base font-semibold">{formatPrice(product.best_price)}</span>
          <span className="text-xs text-slate-500">
            on {PLATFORM_LABEL[product.best_platform] ?? product.best_platform}
          </span>
          {best?.rating && <span className="ml-auto text-xs text-slate-500">★ {Number(best.rating).toFixed(1)}</span>}
        </div>

        {otherListings.length > 0 && (
          <ul className="mt-1 flex flex-col gap-1 border-t border-dashed border-slate-200 pt-2 text-xs">
            {otherListings.map((l) => (
              <PlatformRow key={l.id} listing={l} />
            ))}
          </ul>
        )}
      </div>
    </article>
  );
}

function PlatformRow({ listing }: { listing: Listing }) {
  const label = PLATFORM_LABEL[listing.platform] ?? listing.platform;
  return (
    <li>
      <a
        href={listing.url}
        target="_blank"
        rel="noopener noreferrer nofollow"
        className="flex items-center justify-between gap-2 text-slate-600 hover:text-accent"
      >
        <span className="rounded-full bg-slate-100 px-2 py-0.5 capitalize text-slate-700">{label}</span>
        <span className="font-medium">{formatPrice(listing.price)}</span>
      </a>
    </li>
  );
}
