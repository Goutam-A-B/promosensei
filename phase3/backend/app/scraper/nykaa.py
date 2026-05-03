"""Nykaa product-listing scraper.

Nykaa primarily lists beauty + personal-care SKUs, so cross-platform overlap
with Amazon/Flipkart concentrates around brands like Cetaphil, Lakme,
Mamaearth, Plum. The DOM uses CSS-module class names (`css-…`) which mutate
across builds, so this parser leans on stable structural cues (`<a>` to
`/p/<sku>`, `data-sku`, semantic class fragments like `product-title`).
"""
from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup, Tag

from app.config import get_settings
from app.schemas import ScrapedListing
from app.scraper.normalizer import normalize

logger = logging.getLogger(__name__)

PLATFORM = "nykaa"

_SKU_RE = re.compile(r"/p/(\d+)")


def _extract_sku(url: str | None, fallback: str | None = None) -> str | None:
    if url:
        m = _SKU_RE.search(url)
        if m:
            return m.group(1)
    return fallback


def _abs_url(href: str | None, base: str = "https://www.nykaa.com") -> str | None:
    if not href:
        return None
    if href.startswith("http://") or href.startswith("https://"):
        return href
    if href.startswith("//"):
        return "https:" + href
    if href.startswith("/"):
        return base + href
    return base + "/" + href


def _text(node: Tag | None) -> str | None:
    if node is None:
        return None
    txt = node.get_text(" ", strip=True)
    return txt or None


def _parse_card(card: Tag) -> ScrapedListing | None:
    sku = card.get("data-sku") or card.get("data-product-id") or None

    link = (
        card.select_one("a[href*='/p/']")
        or card.select_one("a.product-title")
        or card.select_one("a")
    )
    href = link.get("href") if link else None
    url = _abs_url(href)

    if not sku:
        sku = _extract_sku(url)
    if not sku or not url:
        return None

    title_node = (
        card.select_one(".product-title")
        or card.select_one("h2")
        or card.select_one(".css-xrzmfa")
    )
    raw_title = _text(title_node)

    price_node = (
        card.select_one(".product-price-offer")
        or card.select_one(".css-111z9ua")
        or card.select_one(".product-price")
    )
    raw_price = _text(price_node)

    original_node = (
        card.select_one(".product-price-mrp")
        or card.select_one(".css-1d0jf8e")
        or card.select_one(".product-mrp")
    )
    raw_original = _text(original_node)

    rating_node = (
        card.select_one(".product-rating")
        or card.select_one(".css-1xy6c70")
    )
    raw_rating = _text(rating_node)

    image_node = (
        card.select_one("img.product-image")
        or card.select_one("img.css-11gn9r6")
        or card.select_one("img")
    )
    image_url = image_node.get("src") if image_node else None

    return normalize(
        platform=PLATFORM,
        platform_product_id=sku,
        raw_title=raw_title or "",
        raw_price=raw_price,
        raw_original_price=raw_original,
        raw_rating=raw_rating,
        url=url,
        image_url=image_url,
    )


def _parse_html(html: str) -> list[ScrapedListing]:
    soup = BeautifulSoup(html, "html.parser")
    cards: Iterable[Tag] = (
        soup.select("div[data-sku]")
        or soup.select("div.product-card")
        or soup.select("a.product-card")
        or soup.select("div.productWrapper")
    )

    seen: set[str] = set()
    results: list[ScrapedListing] = []
    for card in cards:
        listing = _parse_card(card)
        if listing is None:
            continue
        if listing.platform_product_id in seen:
            continue
        seen.add(listing.platform_product_id)
        results.append(listing)
    return results


class NykaaScraper:
    def __init__(
        self,
        *,
        deals_url: str | None = None,
        max_pages: int | None = None,
        page_timeout_ms: int | None = None,
        user_agent: str | None = None,
        use_fixtures: bool | None = None,
        fixtures_dir: Path | None = None,
    ) -> None:
        settings = get_settings()
        self.deals_url = deals_url or settings.scraper_nykaa_deals_url
        self.max_pages = max_pages or settings.scraper_max_pages
        self.page_timeout_ms = page_timeout_ms or settings.scraper_page_timeout_ms
        self.user_agent = user_agent or settings.scraper_user_agent
        self.use_fixtures = (
            settings.scraper_use_fixtures if use_fixtures is None else use_fixtures
        )
        self.fixtures_dir = fixtures_dir or _default_fixtures_dir()

    def scrape(self) -> list[ScrapedListing]:
        if self.use_fixtures:
            return self._scrape_fixtures()
        return self._scrape_live()

    def _scrape_fixtures(self) -> list[ScrapedListing]:
        if not self.fixtures_dir.exists():
            logger.warning("Nykaa fixtures dir %s does not exist", self.fixtures_dir)
            return []
        listings: list[ScrapedListing] = []
        seen: set[str] = set()
        for path in sorted(self.fixtures_dir.glob("*.html")):
            html = path.read_text(encoding="utf-8")
            for listing in _parse_html(html):
                if listing.platform_product_id in seen:
                    continue
                seen.add(listing.platform_product_id)
                listings.append(listing)
        logger.info("Parsed %d Nykaa listings from %s", len(listings), self.fixtures_dir)
        return listings

    def _scrape_live(self) -> list[ScrapedListing]:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "Playwright is required for live scraping. Install with `pip install playwright`."
            ) from exc

        results: list[ScrapedListing] = []
        seen: set[str] = set()

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(user_agent=self.user_agent)
            page = context.new_page()
            page.set_default_timeout(self.page_timeout_ms)

            for page_num in range(1, self.max_pages + 1):
                url = self._page_url(page_num)
                logger.info("Fetching Nykaa page %d: %s", page_num, url)
                try:
                    page.goto(url, wait_until="domcontentloaded")
                    page.wait_for_selector(
                        "div[data-sku], div.product-card, a.product-card",
                        timeout=self.page_timeout_ms,
                    )
                    html = page.content()
                except Exception as exc:
                    logger.warning("Failed Nykaa page %d: %s", page_num, exc)
                    continue

                parsed = _parse_html(html)
                if not parsed:
                    logger.info("Empty Nykaa page %d — assuming end of results", page_num)
                    break
                for listing in parsed:
                    if listing.platform_product_id in seen:
                        continue
                    seen.add(listing.platform_product_id)
                    results.append(listing)

            browser.close()

        logger.info("Nykaa live scrape produced %d unique listings", len(results))
        return results

    def _page_url(self, page_num: int) -> str:
        if page_num <= 1:
            return self.deals_url
        sep = "&" if "?" in self.deals_url else "?"
        return f"{self.deals_url}{sep}page={page_num}"


def _default_fixtures_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "fixtures" / "nykaa"


def scrape_nykaa(**kwargs: Any) -> list[ScrapedListing]:
    return NykaaScraper(**kwargs).scrape()
