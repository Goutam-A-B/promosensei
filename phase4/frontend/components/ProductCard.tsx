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

// Per-platform colour scheme, picked to read like the real brand
// without copying logos. Each platform gets a tinted left-border so
// the rows are scannable at a glance.
const PLATFORM_STYLE: Record<string, { dot: string; border: string }> = {
  amazon: { dot: "bg-orange-500", border: "border-l-orange-500" },
  flipkart: { dot: "bg-blue-500", border: "border-l-blue-500" },
  nykaa: { dot: "bg-pink-500", border: "border-l-pink-500" }
};

export default function ProductCard({ product, showSimilarity = false }: Props) {
  const best =
    product.listings.find((l) => l.platform === product.best_platform) ?? product.listings[0];
  const bestDiscount = best?.discount ? Math.round(Number(best.discount)) : null;
  const similarityPct =
    showSimilarity && product.similarity > 0 ? Math.round(product.similarity * 100) : null;

  // Sort cheapest-first so the "BEST" pill is at the top of the platform list.
  const sortedListings = [...product.listings].sort(
    (a, b) => Number(a.price) - Number(b.price)
  );

  return (
    <article className="group flex flex-col overflow-hidden rounded-2xl bg-white shadow-sm ring-1 ring-slate-200 transition hover:-translate-y-0.5 hover:shadow-md">
      <div className="relative aspect-square w-full overflow-hidden bg-slate-100">
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
          <span className="absolute left-2 top-2 rounded-full bg-emerald-600 px-2 py-0.5 text-xs font-semibold text-white shadow">
            {bestDiscount}% off
          </span>
        )}
        {product.platform_count > 1 && (
          <span className="absolute right-2 top-2 rounded-full bg-slate-900/85 px-2 py-0.5 text-xs font-semibold text-white shadow">
            on {product.platform_count} platforms
          </span>
        )}
      </div>

      <div className="flex flex-1 flex-col gap-2 p-3">
        <div className="flex items-baseline justify-between gap-2">
          {product.brand && (
            <span className="text-xs uppercase tracking-wide text-slate-500">
              {product.brand}
            </span>
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

        {/* Per-platform price ladder: each row is its own link to that
            platform's product/search page. The cheapest listing carries a
            BEST pill. This is the user-facing answer to "I see two
            platforms — let me pick which to open." */}
        <div className="mt-1 flex flex-col gap-1.5">
          {sortedListings.map((l, idx) => (
            <PlatformLink
              key={l.id}
              listing={l}
              isBest={idx === 0 && sortedListings.length > 1}
            />
          ))}
        </div>
      </div>
    </article>
  );
}

function PlatformLink({ listing, isBest }: { listing: Listing; isBest: boolean }) {
  const label = PLATFORM_LABEL[listing.platform] ?? listing.platform;
  const style = PLATFORM_STYLE[listing.platform] ?? {
    dot: "bg-slate-400",
    border: "border-l-slate-400"
  };
  return (
    <a
      href={listing.url}
      target="_blank"
      rel="noopener noreferrer nofollow"
      className={`group/link flex items-center justify-between gap-2 rounded-lg border border-slate-200 border-l-4 ${style.border} bg-slate-50 px-3 py-2 text-sm transition hover:border-slate-300 hover:bg-white hover:shadow-sm`}
    >
      <span className="flex items-center gap-2">
        <span className={`h-2 w-2 rounded-full ${style.dot}`} aria-hidden />
        <span className="font-medium text-slate-800">{label}</span>
        {isBest && (
          <span className="rounded-full bg-emerald-100 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-emerald-700 ring-1 ring-emerald-200">
            best
          </span>
        )}
        {listing.rating && (
          <span className="text-xs text-slate-500">★ {Number(listing.rating).toFixed(1)}</span>
        )}
      </span>
      <span className="flex items-center gap-1.5">
        <span className="font-semibold text-slate-900">{formatPrice(listing.price)}</span>
        <span
          className="text-slate-400 transition group-hover/link:translate-x-0.5 group-hover/link:text-slate-700"
          aria-hidden
        >
          →
        </span>
      </span>
    </a>
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
  { pattern: /iphone|galaxy s|pixel|oneplus|redmi|vivo|oppo|realme|smartphone|mobile|nothing phone/i, emoji: "📱", gradient: "bg-gradient-to-br from-sky-100 to-blue-200" },
  // Tablets
  { pattern: /ipad|galaxy tab|tablet/i, emoji: "📱", gradient: "bg-gradient-to-br from-indigo-100 to-blue-200" },
  // Laptops / PCs
  { pattern: /laptop|macbook|ideapad|inspiron|pavilion|notebook|chromebook/i, emoji: "💻", gradient: "bg-gradient-to-br from-slate-100 to-zinc-200" },
  // Peripherals
  { pattern: /keyboard|mouse|webcam|monitor|printer/i, emoji: "⌨️", gradient: "bg-gradient-to-br from-stone-100 to-stone-200" },
  // Wearables
  { pattern: /watch|smartwatch|band|fitness tracker/i, emoji: "⌚", gradient: "bg-gradient-to-br from-amber-100 to-orange-200" },
  // Home / Kitchen
  { pattern: /air fryer|microwave|refrigerator|washing machine|vacuum|robot vacuum|kettle|toaster|blender|mixer|grinder|oven/i, emoji: "🏠", gradient: "bg-gradient-to-br from-teal-100 to-emerald-200" },
  // TV
  { pattern: /\btv\b|television|smart tv|qled|oled\b/i, emoji: "📺", gradient: "bg-gradient-to-br from-cyan-100 to-sky-200" },
  // Gaming
  { pattern: /playstation|ps5|xbox|nintendo|gaming|controller/i, emoji: "🎮", gradient: "bg-gradient-to-br from-fuchsia-100 to-pink-200" },
  // Cameras
  { pattern: /camera|gopro|dslr|mirrorless|lens/i, emoji: "📷", gradient: "bg-gradient-to-br from-zinc-100 to-slate-200" },
  // Books
  { pattern: /book|hardcover|paperback|\bby [A-Z]/, emoji: "📚", gradient: "bg-gradient-to-br from-orange-100 to-rose-200" },
  // Footwear
  { pattern: /shoe|sneaker|sandal|loafer|boot|footwear/i, emoji: "👟", gradient: "bg-gradient-to-br from-lime-100 to-green-200" },
  // Sports
  { pattern: /yoga|dumbbell|gym|cricket|football|shuttle|racquet|fitness band|exercise/i, emoji: "🏋️", gradient: "bg-gradient-to-br from-emerald-100 to-teal-200" },
  // Skincare
  { pattern: /cleanser|moisturi[sz]|serum|toner|sunscreen|face wash|cream|spf/i, emoji: "🧴", gradient: "bg-gradient-to-br from-emerald-100 to-cyan-200" },
  // Makeup
  { pattern: /lipstick|foundation|kajal|eyeliner|mascara|blush|primer|nail polish/i, emoji: "💄", gradient: "bg-gradient-to-br from-pink-100 to-rose-200" },
  // Haircare
  { pattern: /shampoo|conditioner|hair oil|hair dryer|hair colour|hair color/i, emoji: "💇", gradient: "bg-gradient-to-br from-amber-100 to-yellow-200" },
  // Perfume
  { pattern: /perfume|fragrance|cologne|eau de|deodorant/i, emoji: "🌸", gradient: "bg-gradient-to-br from-rose-100 to-fuchsia-200" },
  // Clothing
  { pattern: /t-shirt|tshirt|shirt|jeans|trouser|kurta|saree|dress\b|hoodie|jacket|sweater|kurti|leggings|polo|innerwear|shorts/i, emoji: "👕", gradient: "bg-gradient-to-br from-rose-100 to-pink-200" },
  // Bags
  { pattern: /backpack|handbag|wallet|luggage|trolley|duffle/i, emoji: "🎒", gradient: "bg-gradient-to-br from-amber-100 to-orange-200" },
  // Stationery
  { pattern: /pen\b|notebook|stationery|diary/i, emoji: "✒️", gradient: "bg-gradient-to-br from-stone-100 to-amber-200" },
  // Drones
  { pattern: /drone|quadcopter/i, emoji: "🚁", gradient: "bg-gradient-to-br from-sky-100 to-cyan-200" },
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
