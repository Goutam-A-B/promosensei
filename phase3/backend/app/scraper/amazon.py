"""Amazon offers scraper.

Two ingest paths:

1. Live: drive a real browser via Playwright against `scraper_amazon_deals_url`.
2. Fixture: parse local HTML snapshots in `fixtures/amazon/`. Used for tests and
   for any environment where Playwright/Chromium is unavailable.

Both paths funnel into the same `_parse_html` function so the parsing logic is
exercised by tests regardless of how the bytes were fetched.
"""
from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup, Tag

from app.config import get_settings
from app.schemas import ScrapedProduct
from app.scraper.normalizer import normalize

logger = logging.getLogger(__name__)

PLATFORM = "amazon"

_ASIN_PATTERNS = [
    re.compile(r"/dp/([A-Z0-9]{10})"),
    re.compile(r"/gp/product/([A-Z0-9]{10})"),
    re.compile(r"data-asin=\"([A-Z0-9]{10})\""),
]


def _extract_asin(url: str | None, fallback: str | None = None) -> str | None:
    if url:
        for pattern in _ASIN_PATTERNS:
            m = pattern.search(url)
            if m:
                return m.group(1)
    if fallback:
        m = re.search(r"[A-Z0-9]{10}", fallback)
        if m:
            return m.group(0)
    return None


def _abs_url(href: str | None, base: str = "https://www.amazon.in") -> str | None:
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


def _parse_card(card: Tag) -> ScrapedProduct | None:
    asin = card.get("data-asin") or None

    link = card.select_one("a[href*='/dp/']") or card.select_one("a.a-link-normal[href]")
    href = link.get("href") if link else None
    url = _abs_url(href)

    if not asin:
        asin = _extract_asin(url, fallback=card.get("id"))

    if not asin or not url:
        return None

    title_node = (
        card.select_one("h2 span")
        or card.select_one(".a-size-base-plus")
        or card.select_one(".a-text-normal")
        or card.select_one("h2")
    )
    raw_title = _text(title_node)

    price_node = (
        card.select_one(".a-price .a-offscreen")
        or card.select_one("span.a-price-whole")
        or card.select_one(".a-color-price")
    )
    raw_price = _text(price_node)

    original_node = card.select_one(".a-text-price .a-offscreen") or card.select_one(
        ".a-text-price"
    )
    raw_original = _text(original_node)

    rating_node = card.select_one("i.a-icon-star span.a-icon-alt") or card.select_one(
        "span.a-icon-alt"
    )
    raw_rating = _text(rating_node)

    image_node = card.select_one("img.s-image") or card.select_one("img")
    image_url = image_node.get("src") if image_node else None

    return normalize(
        platform=PLATFORM,
        platform_product_id=asin,
        raw_title=raw_title or "",
        raw_price=raw_price,
        raw_original_price=raw_original,
        raw_rating=raw_rating,
        url=url,
        image_url=image_url,
    )


def _parse_html(html: str) -> list[ScrapedProduct]:
    soup = BeautifulSoup(html, "html.parser")
    cards: Iterable[Tag] = (
        soup.select("div[data-asin]")
        or soup.select("div.s-result-item")
        or soup.select("li.DealGridItem")
        or soup.select("div.DealCard")
    )

    seen: set[str] = set()
    results: list[ScrapedProduct] = []
    for card in cards:
        product = _parse_card(card)
        if product is None:
            continue
        if product.platform_product_id in seen:
            continue
        seen.add(product.platform_product_id)
        results.append(product)
    return results


class AmazonScraper:
    """Scraper that supports both live (Playwright) and fixture-based runs."""

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
        self.deals_url = deals_url or settings.scraper_amazon_deals_url
        self.max_pages = max_pages or settings.scraper_max_pages
        self.page_timeout_ms = page_timeout_ms or settings.scraper_page_timeout_ms
        self.user_agent = user_agent or settings.scraper_user_agent
        self.use_fixtures = (
            settings.scraper_use_fixtures if use_fixtures is None else use_fixtures
        )
        self.fixtures_dir = fixtures_dir or _default_fixtures_dir()

    def scrape(self) -> list[ScrapedProduct]:
        if self.use_fixtures:
            return self._scrape_fixtures()
        return self._scrape_live()

    def _scrape_fixtures(self) -> list[ScrapedProduct]:
        if not self.fixtures_dir.exists():
            logger.warning("Fixtures dir %s does not exist", self.fixtures_dir)
            return []
        products: list[ScrapedProduct] = []
        seen: set[str] = set()
        for path in sorted(self.fixtures_dir.glob("*.html")):
            html = path.read_text(encoding="utf-8")
            for product in _parse_html(html):
                if product.platform_product_id in seen:
                    continue
                seen.add(product.platform_product_id)
                products.append(product)
        logger.info("Parsed %d products from fixtures in %s", len(products), self.fixtures_dir)
        return products

    def _scrape_live(self) -> list[ScrapedProduct]:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:  # pragma: no cover - exercised only in live runs
            raise RuntimeError(
                "Playwright is required for live scraping. Install with `pip install playwright`."
            ) from exc

        results: list[ScrapedProduct] = []
        seen: set[str] = set()

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(user_agent=self.user_agent)
            page = context.new_page()
            page.set_default_timeout(self.page_timeout_ms)

            for page_num in range(1, self.max_pages + 1):
                url = self._page_url(page_num)
                logger.info("Fetching Amazon page %d: %s", page_num, url)
                try:
                    page.goto(url, wait_until="domcontentloaded")
                    page.wait_for_selector("div[data-asin], div.DealCard", timeout=self.page_timeout_ms)
                    html = page.content()
                except Exception as exc:
                    logger.warning("Failed page %d: %s", page_num, exc)
                    continue

                parsed = _parse_html(html)
                if not parsed:
                    logger.info("Empty page %d — assuming end of results", page_num)
                    break
                for product in parsed:
                    if product.platform_product_id in seen:
                        continue
                    seen.add(product.platform_product_id)
                    results.append(product)

            browser.close()

        logger.info("Live scrape produced %d unique products", len(results))
        return results

    def _page_url(self, page_num: int) -> str:
        if page_num <= 1:
            return self.deals_url
        sep = "&" if "?" in self.deals_url else "?"
        return f"{self.deals_url}{sep}page={page_num}"


def _default_fixtures_dir() -> Path:
    # app/scraper/amazon.py → app/scraper → app → backend → backend/fixtures/amazon
    return Path(__file__).resolve().parents[2] / "fixtures" / "amazon"


def scrape_amazon(**kwargs: Any) -> list[ScrapedProduct]:
    return AmazonScraper(**kwargs).scrape()
