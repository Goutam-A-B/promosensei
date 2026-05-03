from app.scraper.amazon import AmazonScraper, scrape_amazon
from app.scraper.normalizer import (
    clean_title,
    compute_discount,
    normalize,
    parse_price,
    parse_rating,
)
from app.scraper.persistence import upsert_products

__all__ = [
    "AmazonScraper",
    "scrape_amazon",
    "clean_title",
    "compute_discount",
    "normalize",
    "parse_price",
    "parse_rating",
    "upsert_products",
]
