from app.scraper.amazon import AmazonScraper, scrape_amazon
from app.scraper.flipkart import FlipkartScraper, scrape_flipkart
from app.scraper.normalizer import (
    clean_title,
    compute_discount,
    normalize,
    parse_price,
    parse_rating,
)
from app.scraper.nykaa import NykaaScraper, scrape_nykaa
from app.scraper.persistence import refresh_prices, upsert_listings, upsert_products

__all__ = [
    "AmazonScraper",
    "FlipkartScraper",
    "NykaaScraper",
    "clean_title",
    "compute_discount",
    "normalize",
    "parse_price",
    "parse_rating",
    "refresh_prices",
    "scrape_amazon",
    "scrape_flipkart",
    "scrape_nykaa",
    "upsert_listings",
    "upsert_products",
]
