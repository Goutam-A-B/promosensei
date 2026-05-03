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
          <CategoryPlaceholder
            title={product.canonical_title}
            brand={product.brand}
            seed={product.id}
          />
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

// Demo catalogue has no real product images (we don't hotlink retailer
// CDNs — fragile, ToS-questionable). The fallback is a category-aware
// tile: large emoji for visual context, brand wordmark below, tinted
// gradient picked deterministically per product so the grid looks varied.
//
// Tailwind's JIT only sees classes that appear as literal strings, so we
// inline the full classnames here rather than building them dynamically.
const CATEGORY_RULES: Array<{ pattern: RegExp; emoji: string; gradient: string }> = [
  // Audio
  { pattern: /headphone|headset|earbud|airpod|airdopes|buds|speaker/i, emoji: "🎧", gradient: "bg-gradient-to-br from-violet-100 to-indigo-200" },
  // Phones
  { pattern: /iphone|galaxy s|pixel|oneplus|redmi|vivo|oppo|realme|smartphone|mobile/i, emoji: "📱", gradient: "bg-gradient-to-br from-sky-100 to-blue-200" },
  // Laptops / PCs
  { pattern: /laptop|macbook|ideapad|inspiron|pavilion|notebook|chromebook/i, emoji: "💻", gradient: "bg-gradient-to-br from-slate-100 to-zinc-200" },
  // Peripherals
  { pattern: /keyboard|mouse|webcam|monitor|printer/i, emoji: "⌨️", gradient: "bg-gradient-to-br from-stone-100 to-stone-200" },
  // Wearables
  { pattern: /watch|smartwatch|band|fitness tracker/i, emoji: "⌚", gradient: "bg-gradient-to-br from-amber-100 to-orange-200" },
  // Home / Kitchen
  { pattern: /air fryer|microwave|refrigerator|washing machine|vacuum|robot vacuum|kettle|toaster|blender|mixer/i, emoji: "🏠", gradient: "bg-gradient-to-br from-teal-100 to-emerald-200" },
  // TV
  { pattern: /\btv\b|television|smart tv|qled|oled\b/i, emoji: "📺", gradient: "bg-gradient-to-br from-cyan-100 to-sky-200" },
  // Gaming
  { pattern: /playstation|ps5|xbox|nintendo|gaming|controller/i, emoji: "🎮", gradient: "bg-gradient-to-br from-fuchsia-100 to-pink-200" },
  // Cameras
  { pattern: /camera|gopro|dslr|mirrorless|lens/i, emoji: "📷", gradient: "bg-gradient-to-br from-zinc-100 to-slate-200" },
  // Books
  { pattern: /book|hardcover|paperback|by [A-Z]/, emoji: "📚", gradient: "bg-gradient-to-br from-orange-100 to-rose-200" },
  // Footwear
  { pattern: /shoe|sneaker|sandal|loafer|boot|footwear/i, emoji: "👟", gradient: "bg-gradient-to-br from-lime-100 to-green-200" },
  // Sports
  { pattern: /yoga|dumbbell|gym|sports|cricket|football|shuttle|racquet/i, emoji: "🏋️", gradient: "bg-gradient-to-br from-emerald-100 to-teal-200" },
  // Skincare
  { pattern: /cleanser|moisturi[sz]|serum|toner|sunscreen|face wash|cream/i, emoji: "🧴", gradient: "bg-gradient-to-br from-emerald-100 to-cyan-200" },
  // Makeup
  { pattern: /lipstick|foundation|kajal|eyeliner|mascara|blush|primer/i, emoji: "💄", gradient: "bg-gradient-to-br from-pink-100 to-rose-200" },
  // Haircare
  { pattern: /shampoo|conditioner|hair oil|hair dryer/i, emoji: "💇", gradient: "bg-gradient-to-br from-amber-100 to-yellow-200" },
  // Perfume
  { pattern: /perfume|fragrance|cologne|eau de/i, emoji: "🌸", gradient: "bg-gradient-to-br from-rose-100 to-fuchsia-200" },
  // Stationery
  { pattern: /pen\b|notebook|stationery|diary/i, emoji: "✒️", gradient: "bg-gradient-to-br from-stone-100 to-amber-200" },
];

const FALLBACK_GRADIENTS = [
  "bg-gradient-to-br from-rose-100 to-rose-200",
  "bg-gradient-to-br from-amber-100 to-amber-200",
  "bg-gradient-to-br from-emerald-100 to-emerald-200",
  "bg-gradient-to-br from-sky-100 to-sky-200",
  "bg-gradient-to-br from-violet-100 to-violet-200",
  "bg-gradient-to-br from-fuchsia-100 to-fuchsia-200",
  "bg-gradient-to-br from-teal-100 to-teal-200",
  "bg-gradient-to-br from-orange-100 to-orange-200",
];

function classifyCategory(title: string): { emoji: string; gradient: string } {
  for (const rule of CATEGORY_RULES) {
    if (rule.pattern.test(title)) return { emoji: rule.emoji, gradient: rule.gradient };
  }
  return { emoji: "🛍️", gradient: "" };
}

function CategoryPlaceholder({
  title,
  brand,
  seed,
}: {
  title: string;
  brand: string | null;
  seed: number;
}) {
  const { emoji, gradient } = classifyCategory(title);
  const finalGradient = gradient || FALLBACK_GRADIENTS[seed % FALLBACK_GRADIENTS.length];
  return (
    <div className={`relative flex h-full flex-col items-center justify-center ${finalGradient}`}>
      <div className="text-6xl drop-shadow-sm transition-transform duration-200 group-hover:scale-110">
        {emoji}
      </div>
      {brand && (
        <div className="mt-3 rounded-full bg-white/80 px-3 py-0.5 text-[11px] font-medium uppercase tracking-wide text-slate-700 ring-1 ring-white/60 backdrop-blur-sm">
          {brand}
        </div>
      )}
    </div>
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
