"""Brand, model-number, pack-size, and bundle/refurbished detection.

This is the *cheap* signal layer of the matcher. Everything here is regex
and dictionary lookup — no embeddings, no DB. Decisions feed into the more
expensive cosine-similarity step in `canonicalize.py`.

Edge cases handled here:
- 3.2 Different products, similar titles → model number is weighted heavily
       so "WH-1000XM4" and "WH-1000XM5" never match on title alone.
- 3.3 Bundle vs single                  → `is_bundle` flags combos to keep
       them out of the canonical group.
- 3.4 Refurbished / renewed             → `is_refurbished` keeps used
       items from being grouped with new ones.
- 3.5 Pack-size confusion               → 250ml vs 500ml are not the same
       canonical product even when titles otherwise match.
"""
from __future__ import annotations

import re

# A small Indian-market lexicon. Long enough to cover the demo catalog;
# easily extended via config when new categories arrive. Listed here in
# priority order so multi-word brands win over single-word fragments
# ("Mi Smart Band" should match "Mi", not get split into separate words).
KNOWN_BRANDS: tuple[str, ...] = (
    # Electronics
    "Apple", "Samsung", "Sony", "boAt", "JBL", "Bose", "Sennheiser",
    "OnePlus", "Xiaomi", "Mi", "Realme", "Oppo", "Vivo", "Nothing",
    "Asus", "Lenovo", "HP", "Dell", "Acer", "MSI", "Razer",
    "Logitech", "Microsoft", "Google", "Amazon Basics", "Amazfit",
    "Noise", "Fire-Boltt", "Garmin", "Fitbit",
    "LG", "Panasonic", "Philips", "Bosch", "Whirlpool", "Haier",
    "Canon", "Nikon", "GoPro", "DJI",
    # Beauty / personal care
    "Lakme", "Maybelline", "L'Oreal", "Loreal", "MAC", "NYX", "Sugar",
    "Mamaearth", "Plum", "The Body Shop", "Nivea", "Ponds", "Pond's",
    "Cetaphil", "Neutrogena", "Olay", "Dove", "Himalaya",
    "Forest Essentials", "Kiehl's", "Estee Lauder", "Lancome",
    "Bobbi Brown", "Clinique", "Charlotte Tilbury",
    # Apparel / lifestyle (fragments — matcher uses these as low-confidence signals)
    "Nike", "Adidas", "Puma", "Reebok", "Skechers", "Bata",
    # Generic high-frequency
    "Wildcraft", "American Tourister", "VIP", "Skybags",
)

# Compiled once. Word-boundary on both ends, case-insensitive.
_BRAND_RE = re.compile(
    r"(?<![A-Za-z0-9])(" + "|".join(re.escape(b) for b in KNOWN_BRANDS) + r")(?![A-Za-z0-9])",
    re.IGNORECASE,
)

# Model numbers: alpha-numeric tokens with at least one digit and one letter,
# usually hyphenated. Examples: "WH-1000XM5", "MQ8F2HN/A", "RT45T5532S8".
# We tighten by requiring the token to contain at least one digit so plain
# words don't qualify. Length 4-32 to avoid both noise and SKU stuffing.
_MODEL_RE = re.compile(
    r"(?<![A-Za-z0-9])"
    r"(?=[A-Z0-9-]*[A-Z])(?=[A-Z0-9-]*\d)"
    r"[A-Z0-9](?:[A-Z0-9-]{2,30}[A-Z0-9])"
    r"(?![A-Za-z0-9])"
)

# Pack sizes: "250ml", "500 g", "1 kg", "2 pack", "60 capsules".
_PACK_RE = re.compile(
    r"(?<![A-Za-z0-9])"
    r"(?P<num>\d+(?:\.\d+)?)\s*"
    r"(?P<unit>ml|l|g|kg|mg|oz|lb|pack|packs|capsules|tablets|count|ct|pieces|pcs)"
    r"(?![A-Za-z0-9])",
    re.IGNORECASE,
)

_BUNDLE_TOKENS = (
    "combo", "bundle", "pack of", "set of", "with case", "with cover",
    "with charger", "with strap", "+ ", "& ", "twin pack",
)

_REFURB_TOKENS = (
    "refurbished", "renewed", "pre-owned", "preowned", "used", "open box",
    "openbox", "second hand", "secondhand",
)


def extract_brand(title: str) -> str | None:
    """Return the canonical brand name as it appears in `KNOWN_BRANDS`."""
    if not title:
        return None
    m = _BRAND_RE.search(title)
    if not m:
        return None
    matched = m.group(1)
    # Normalize to the canonical casing from KNOWN_BRANDS.
    for canonical in KNOWN_BRANDS:
        if canonical.lower() == matched.lower():
            return canonical
    return matched


def extract_model_number(title: str) -> str | None:
    """Return the longest plausible model number in `title`, uppercase."""
    if not title:
        return None
    candidates = _MODEL_RE.findall(title.upper())
    if not candidates:
        return None
    # Longest wins — model numbers tend to be the most specific token.
    candidates.sort(key=len, reverse=True)
    return candidates[0]


def extract_pack_size(title: str) -> str | None:
    """Return a normalized "<num><unit>" string, e.g. "250ml", or None."""
    if not title:
        return None
    m = _PACK_RE.search(title)
    if not m:
        return None
    num = m.group("num")
    # Strip a trailing ".0" so "1.0kg" becomes "1kg".
    if num.endswith(".0"):
        num = num[:-2]
    unit = m.group("unit").lower()
    # Canonicalize unit aliases.
    unit = {"pcs": "pieces", "ct": "count", "packs": "pack", "tablets": "tablets"}.get(unit, unit)
    return f"{num}{unit}"


def is_bundle(title: str) -> bool:
    if not title:
        return False
    lowered = title.lower()
    return any(tok in lowered for tok in _BUNDLE_TOKENS)


def is_refurbished(title: str) -> bool:
    if not title:
        return False
    lowered = title.lower()
    return any(tok in lowered for tok in _REFURB_TOKENS)
