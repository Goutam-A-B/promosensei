import re
from decimal import Decimal, InvalidOperation

from app.schemas import ScrapedProduct

_NOISE_PATTERNS = [
    re.compile(r"\[[^\]]*(sponsored|limited deal|best seller|deal of the day)[^\]]*\]", re.IGNORECASE),
    re.compile(r"\([^\)]*(sponsored|limited deal|best seller|deal of the day)[^\)]*\)", re.IGNORECASE),
    re.compile(r"\bsponsored\b", re.IGNORECASE),
    re.compile(r"\blimited deal\b!?", re.IGNORECASE),
    re.compile(r"\bbest seller\b", re.IGNORECASE),
    re.compile(r"\bdeal of the day\b", re.IGNORECASE),
]
_WHITESPACE = re.compile(r"\s+")
# Keep digits and a single decimal separator. Drop currency symbols, letters,
# and stray punctuation (like the dot in "Rs.").
_PRICE_KEEP = re.compile(r"[^\d.]")
_PRICE_LEADING_NOISE = re.compile(r"^[^\d]*")


def clean_title(raw: str) -> str:
    title = raw or ""
    for pattern in _NOISE_PATTERNS:
        title = pattern.sub("", title)
    title = _WHITESPACE.sub(" ", title).strip(" -|–—[]()!")
    return title


def parse_price(raw: str | None) -> Decimal | None:
    if raw is None:
        return None
    text = str(raw).replace(",", "")
    # Strip non-numeric prefix (e.g. "Rs.", "₹", "INR ") so the price's leading
    # decimal point isn't confused with a currency-token dot.
    text = _PRICE_LEADING_NOISE.sub("", text)
    cleaned = _PRICE_KEEP.sub("", text)
    if not cleaned or cleaned == ".":
        return None
    # Reject ambiguous multi-decimal strings like "1.2.3".
    if cleaned.count(".") > 1:
        return None
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        return None
    if value < 0:
        return None
    return value.quantize(Decimal("0.01"))


def parse_rating(raw: str | None) -> Decimal | None:
    if raw is None:
        return None
    match = re.search(r"(\d+(?:\.\d+)?)", str(raw))
    if not match:
        return None
    try:
        value = Decimal(match.group(1))
    except InvalidOperation:
        return None
    if value < 0 or value > 5:
        return None
    return value.quantize(Decimal("0.01"))


def compute_discount(price: Decimal, original_price: Decimal | None) -> Decimal | None:
    """Trust the math, not the label. Returns percent or None."""
    if original_price is None or original_price <= 0:
        return None
    if original_price <= price:
        return None
    pct = (original_price - price) / original_price * Decimal(100)
    return pct.quantize(Decimal("0.01"))


def normalize(
    *,
    platform: str,
    platform_product_id: str,
    raw_title: str,
    raw_price: str | None,
    raw_original_price: str | None,
    raw_rating: str | None,
    url: str,
    image_url: str | None,
) -> ScrapedProduct | None:
    """Build a ScrapedProduct or return None if required fields are unusable."""
    title = clean_title(raw_title)
    price = parse_price(raw_price)

    if not title or price is None or not platform_product_id or not url:
        return None

    original_price = parse_price(raw_original_price)
    if original_price is not None and original_price <= price:
        original_price = None

    discount = compute_discount(price, original_price)
    if discount is not None and discount > Decimal(90):
        # Implausibly large discount — likely a price-extraction bug. Drop the discount,
        # keep the row so the user still sees the listing.
        discount = None
        original_price = None

    rating = parse_rating(raw_rating)

    return ScrapedProduct(
        platform=platform,
        platform_product_id=platform_product_id,
        title=title[:1024],
        price=price,
        original_price=original_price,
        discount=discount,
        rating=rating,
        url=url[:2048],
        image_url=image_url[:2048] if image_url else None,
    )
