"""Pre-parse natural-language queries into structured filters + a residual.

Edge case 4.5 (docs/edge-cases.md):

    "earbuds under 2000"           -> max_price=2000, residual="earbuds"
    "phones between 5k and 10k"    -> min_price=5000, max_price=10000, residual="phones"
    "4-star moisturizer under ₹3000" -> min_rating=4, max_price=3000, residual="moisturizer"

Why pre-parse instead of letting the embedding handle it? Two reasons:

1. Numeric constraints are a *filter* signal, not a similarity signal — a
   ₹3000 lipstick shouldn't outrank a ₹500 lipstick on a "below ₹500" query.
2. Keeping the constraint out of the residual gives the embedding a cleaner
   intent vector ("moisturizer" embeds far better than "4-star moisturizer
   under ₹3000").
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal


@dataclass
class ParsedQuery:
    residual: str
    min_price: Decimal | None = None
    max_price: Decimal | None = None
    min_rating: Decimal | None = None
    notes: list[str] = field(default_factory=list)


# Order matters: more-specific patterns first.
_RANGE = re.compile(
    r"\bbetween\s+(?:rs\.?|inr|₹)?\s*(?P<lo>\d[\d,\.]*)\s*(?P<lou>k|thousand)?\s*"
    r"(?:and|to|-|–)\s*(?:rs\.?|inr|₹)?\s*(?P<hi>\d[\d,\.]*)\s*(?P<hiu>k|thousand)?\b",
    re.IGNORECASE,
)
_BELOW = re.compile(
    r"\b(?:under|below|less than|<=?|upto|up to|within|cheaper than)\s*"
    r"(?:rs\.?|inr|₹)?\s*(?P<v>\d[\d,\.]*)\s*(?P<u>k|thousand)?\b",
    re.IGNORECASE,
)
_ABOVE = re.compile(
    r"\b(?:over|above|more than|>=?|atleast|at least|minimum|min)\s*"
    r"(?:rs\.?|inr|₹)?\s*(?P<v>\d[\d,\.]*)\s*(?P<u>k|thousand)?\b",
    re.IGNORECASE,
)
_RATING = re.compile(
    r"\b(?P<v>[1-5](?:\.\d)?)\s*[-+]?\s*(?:star|stars|★)\b(?:\s*(?:rated|and above|or above))?",
    re.IGNORECASE,
)
_RATING_ALT = re.compile(
    r"\b(?:rated|rating)\s*(?:>=|above|over|min(?:imum)?)\s*(?P<v>[1-5](?:\.\d)?)\b",
    re.IGNORECASE,
)
_BARE_PRICE_RUPEE = re.compile(
    r"(?P<v>(?:rs\.?|inr|₹)\s*\d[\d,\.]*\s*(?:k|thousand)?)",
    re.IGNORECASE,
)


def _to_decimal(raw: str, unit: str | None) -> Decimal | None:
    cleaned = raw.replace(",", "").strip()
    if not cleaned:
        return None
    try:
        value = Decimal(cleaned)
    except Exception:
        return None
    if unit and unit.lower() in {"k", "thousand"}:
        value *= Decimal(1000)
    if value < 0:
        return None
    return value


def parse_query(raw: str) -> ParsedQuery:
    text = (raw or "").strip()
    if not text:
        return ParsedQuery(residual="")

    parsed = ParsedQuery(residual=text)

    def consume(pattern: re.Pattern[str]) -> list[re.Match[str]]:
        matches = list(pattern.finditer(parsed.residual))
        if matches:
            # Remove all spans in one pass, last to first.
            chunks = parsed.residual
            for m in reversed(matches):
                chunks = chunks[: m.start()] + " " + chunks[m.end() :]
            parsed.residual = chunks
        return matches

    # 1. between X and Y  (capture range first to avoid double-eating)
    for m in consume(_RANGE):
        lo = _to_decimal(m.group("lo"), m.group("lou"))
        hi = _to_decimal(m.group("hi"), m.group("hiu"))
        if lo is not None and hi is not None:
            if lo > hi:
                lo, hi = hi, lo
            parsed.min_price = max(parsed.min_price or lo, lo)
            parsed.max_price = min(parsed.max_price or hi, hi)
            parsed.notes.append(f"price between {lo} and {hi}")

    # 2. rating phrases — consume *before* the generic _ABOVE / _BELOW patterns
    # so that "rated above 4" doesn't get eaten as a price.
    for m in consume(_RATING):
        v = _to_decimal(m.group("v"), None)
        if v is not None and v <= 5:
            parsed.min_rating = max(parsed.min_rating or v, v)
            parsed.notes.append(f"min_rating={v}")
    for m in consume(_RATING_ALT):
        v = _to_decimal(m.group("v"), None)
        if v is not None and v <= 5:
            parsed.min_rating = max(parsed.min_rating or v, v)
            parsed.notes.append(f"min_rating={v}")

    # 3. under / below / <=
    for m in consume(_BELOW):
        v = _to_decimal(m.group("v"), m.group("u"))
        if v is not None:
            parsed.max_price = min(parsed.max_price or v, v)
            parsed.notes.append(f"max_price={v}")

    # 4. over / above / >=
    for m in consume(_ABOVE):
        v = _to_decimal(m.group("v"), m.group("u"))
        if v is not None:
            parsed.min_price = max(parsed.min_price or v, v)
            parsed.notes.append(f"min_price={v}")

    # 5. bare currency phrases like "₹2000" we left alone — strip them so the
    #    residual reads cleanly when handed to the embedder.
    consume(_BARE_PRICE_RUPEE)

    # Final tidy-up of the residual.
    parsed.residual = re.sub(r"\s+", " ", parsed.residual).strip(" -|,.;:")
    return parsed
