"""Seed the database with a curated demo catalogue.

Used for the live deploy. Unlike `seed_db.py` (which parses local
fixture HTML), this script writes a hand-curated set of ≈120 products
across electronics, beauty, fashion, home, and sports — chosen so the
matcher, semantic search, filters, and per-platform price ladder all
have something interesting to show a recruiter clicking around.

Why curated instead of live-scraped:
- Amazon / Flipkart / Nykaa block bots aggressively and forbid scraping
  in their ToS. A demo deploy that scrapes them would IP-ban itself
  within hours and serve a recruiter a stale page.
- The scrapers (in `app/scraper/`) are real, tested code — they parse
  the same HTML structures the live sites use. The fixtures cover the
  edge-cases. This script just substitutes a stable data source for
  the *demo path*, with the rest of the pipeline (matcher → index →
  search → cache → metrics) running for real.

Idempotent: rerunning updates prices in place rather than creating
duplicates. `--reset` drops the catalog first.
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.embeddings import reindex_products  # noqa: E402
from app.scraper import upsert_listings  # noqa: E402
from app.schemas import ScrapedListing  # noqa: E402


# ---- Catalogue ------------------------------------------------------------


def _l(platform: str, pid: str, price: float, *, original: float | None = None,
       discount: float | None = None, rating: float | None = None,
       url: str | None = None, image: str | None = None) -> dict:
    return dict(
        platform=platform, pid=pid, price=price, original=original,
        discount=discount, rating=rating, url=url, image=image,
    )


# Each entry: (canonical_title, listings)
# Multi-platform entries demonstrate the matcher + per-platform price ladder.
CATALOGUE: list[tuple[str, list[dict]]] = [
    # ---- Electronics: Audio ---------------------------------------------
    ("Sony WH-1000XM5 Wireless Noise Cancellation Headphones Black", [
        _l("amazon", "B09Y2MZWXY", 26990, original=34990, discount=22.86, rating=4.5),
        _l("flipkart", "ACCKT8UFPEZ6GXHZ", 25990, original=34990, discount=25.72, rating=4.4),
    ]),
    ("Sony WH-1000XM4 Wireless Noise Cancellation Headphones Silver", [
        _l("amazon", "B08C7KG5LP", 19990, original=29990, discount=33.34, rating=4.5),
        _l("flipkart", "ACCFW6S6F5HZJZ7G", 19490, original=29990, discount=35.01, rating=4.4),
    ]),
    ("Apple AirPods Pro 2nd Generation with USB-C", [
        _l("amazon", "B0CHWRXH8B", 22900, original=26900, discount=14.87, rating=4.6),
        _l("flipkart", "ACCGTVZ7XCZRGGRK", 22499, original=26900, discount=16.36, rating=4.5),
    ]),
    ("Samsung Galaxy Buds 2 Pro Bluetooth Earbuds with Mic Graphite", [
        _l("amazon", "B0BFW6JJ16", 12999, original=17990, discount=27.74, rating=4.4),
        _l("flipkart", "ACCGEZV3ZRPHVH3Q", 13499, original=17990, discount=24.97, rating=4.3),
    ]),
    ("boAt Airdopes 141 Bluetooth Truly Wireless Earbuds with 42H Playtime", [
        _l("amazon", "B09N3ZNHTY", 1299, original=2990, discount=56.55, rating=4.1),
        _l("flipkart", "ACCG7B7QHGSCH8YH", 1199, original=2990, discount=59.90, rating=4.0),
    ]),
    ("OnePlus Nord Buds 2 True Wireless Earbuds Thunder Gray", [
        _l("amazon", "B0C2H7FYD8", 2499, original=3499, discount=28.57, rating=4.2),
    ]),
    ("JBL Tune 760NC Wireless Over-Ear Active Noise Cancelling Headphones", [
        _l("amazon", "B09JP9MV1Y", 6999, original=14999, discount=53.34, rating=4.3),
        _l("flipkart", "ACCG9XYJKMHHFKZG", 7299, original=14999, discount=51.34, rating=4.2),
    ]),
    ("Sennheiser HD 458BT Bluetooth Wireless Headphones", [
        _l("amazon", "B08FHYFFK1", 9990, original=14990, discount=33.36, rating=4.3),
    ]),
    ("Marshall Emberton II Portable Bluetooth Speaker Black", [
        _l("amazon", "B0B384RQHV", 14999, original=17999, discount=16.67, rating=4.6),
    ]),
    ("boAt Stone 1200F Bluetooth Speaker 14W RMS", [
        _l("amazon", "B0BLNSZ87C", 2199, original=4990, discount=55.93, rating=4.0),
        _l("flipkart", "ACCGXCV6XKGGFFB7", 1999, original=4990, discount=59.94, rating=4.0),
    ]),

    # ---- Electronics: Phones -------------------------------------------
    ("Apple iPhone 15 (128 GB) Blue", [
        _l("amazon", "B0CHX2ZDRJ", 66999, original=79900, discount=16.15, rating=4.6),
        _l("flipkart", "MOBGTAGPFZWHZWHZ", 65999, original=79900, discount=17.40, rating=4.6),
    ]),
    ("Apple iPhone 15 Pro (256 GB) Natural Titanium", [
        _l("amazon", "B0CHX1W1XY", 144900, original=144900, rating=4.7),
        _l("flipkart", "MOBGTV3ZVHGGZGHN", 142900, original=144900, discount=1.40, rating=4.7),
    ]),
    ("Samsung Galaxy S24 Ultra 5G (256 GB) Titanium Black", [
        _l("amazon", "B0CSL31R8R", 119999, original=134999, discount=11.11, rating=4.5),
        _l("flipkart", "MOBGZGFXKGZHFGZA", 118000, original=134999, discount=12.59, rating=4.5),
    ]),
    ("OnePlus 12R 5G (256 GB) Cool Blue", [
        _l("amazon", "B0CSGNRD4B", 42999, original=45999, discount=6.52, rating=4.4),
        _l("flipkart", "MOBGGBVZKZHHFGFV", 41999, original=45999, discount=8.70, rating=4.4),
    ]),
    ("Google Pixel 8a (128 GB) Aloe", [
        _l("amazon", "B0D2KVRL9T", 49999, original=52999, discount=5.66, rating=4.3),
        _l("flipkart", "MOBGZHFGKHZGFHFB", 48999, original=52999, discount=7.55, rating=4.3),
    ]),
    ("Xiaomi Redmi Note 13 Pro 5G (128 GB) Midnight Black", [
        _l("amazon", "B0CN3GDSCC", 24999, original=29999, discount=16.67, rating=4.2),
        _l("flipkart", "MOBGZ3GFKBHZFGZH", 23999, original=29999, discount=20.00, rating=4.2),
    ]),

    # ---- Electronics: Laptops & PCs ------------------------------------
    ("Apple MacBook Air M2 (8 GB / 256 GB) Midnight 13.6 inch", [
        _l("amazon", "B0B3C2R8MP", 89990, original=114900, discount=21.68, rating=4.7),
        _l("flipkart", "COMGTAFXKZHFGZBV", 89500, original=114900, discount=22.11, rating=4.7),
    ]),
    ("Lenovo IdeaPad Slim 3 Intel Core i5 12th Gen 12450H Laptop 16 GB / 512 GB SSD", [
        _l("amazon", "B0CV8M3BCN", 54990, original=85990, discount=36.06, rating=4.2),
        _l("flipkart", "COMGGB3HFKZGFHFB", 52990, original=85990, discount=38.38, rating=4.2),
    ]),
    ("HP Pavilion x360 14-inch 2-in-1 Touchscreen Laptop Intel Core i5", [
        _l("amazon", "B0BN3ZCK5G", 64990, original=84999, discount=23.54, rating=4.3),
    ]),
    ("Dell Inspiron 15 3520 Intel Core i3 12th Gen Laptop", [
        _l("amazon", "B0CG1BQYJZ", 36990, original=49990, discount=26.00, rating=4.1),
        _l("flipkart", "COMGZHFKGZBHFGFR", 35990, original=49990, discount=28.01, rating=4.1),
    ]),
    ("Logitech MX Master 3S Wireless Performance Mouse", [
        _l("amazon", "B0B12J2LQR", 8995, original=10495, discount=14.29, rating=4.7),
    ]),
    ("Logitech MX Keys S Wireless Keyboard", [
        _l("amazon", "B0B12HCNN6", 9995, original=12995, discount=23.09, rating=4.6),
    ]),

    # ---- Electronics: Wearables & Accessories --------------------------
    ("Apple Watch Series 9 GPS 45mm Midnight Aluminium Case Sport Band", [
        _l("amazon", "B0CHX59M7Y", 41900, original=46900, discount=10.66, rating=4.6),
        _l("flipkart", "ACCGZHFGKHZGFB3J", 40900, original=46900, discount=12.79, rating=4.6),
    ]),
    ("Samsung Galaxy Watch 6 Bluetooth (44 mm) Graphite", [
        _l("amazon", "B0CB22HG4K", 27999, original=33999, discount=17.65, rating=4.4),
        _l("flipkart", "ACCGZ3HFGFBHFGZA", 26999, original=33999, discount=20.59, rating=4.4),
    ]),
    ("Mi Smart Band 7 Fitness Tracker — 1.62 inch AMOLED Black", [
        _l("amazon", "B0B7DVRD7G", 2799, original=3999, discount=30.01, rating=4.3),
        _l("flipkart", "ACCGZHGKHZGFBJ73", 2599, original=3999, discount=35.01, rating=4.3),
    ]),
    ("Noise ColorFit Pulse Grand Smartwatch with 1.69 inch Display", [
        _l("amazon", "B0B36XJD8H", 1499, original=4999, discount=70.01, rating=4.0),
        _l("flipkart", "ACCGFHGZBHFGZAJ7", 1399, original=4999, discount=72.01, rating=4.0),
    ]),

    # ---- Electronics: TV & Home ----------------------------------------
    ("OnePlus Y Series 108 cm (43 inch) Full HD LED Smart Android TV", [
        _l("amazon", "B0B5W6XCVH", 22999, original=30999, discount=25.81, rating=4.3),
        _l("flipkart", "TVSGZ3HFGZBHFGZA", 21999, original=30999, discount=29.04, rating=4.3),
    ]),
    ("LG OLED C3 65 inch 4K UHD Smart TV with WebOS", [
        _l("amazon", "B0BVQHTV2D", 169990, original=259990, discount=34.62, rating=4.7),
    ]),
    ("Mi Q1 75 inch 4K Ultra HD QLED Smart Android TV", [
        _l("flipkart", "TVSGZHFGFBHFGZAQ", 99999, original=149999, discount=33.33, rating=4.4),
    ]),
    ("Bosch Series 4 7 kg Front Load Fully Automatic Washing Machine", [
        _l("amazon", "B07H5RCCMW", 33990, original=45990, discount=26.09, rating=4.2),
        _l("flipkart", "WMGZ3HFGFBHFGFB7", 32990, original=45990, discount=28.27, rating=4.2),
    ]),
    ("LG 195 L 4 Star Inverter Direct Cool Single Door Refrigerator", [
        _l("amazon", "B09KS8YJ3G", 17490, original=22990, discount=23.92, rating=4.3),
        _l("flipkart", "RFGZHFGFBHFGZAJ7", 17290, original=22990, discount=24.79, rating=4.3),
    ]),
    ("Philips Air Fryer HD9252/90 with Rapid Air Technology 4.1L", [
        _l("amazon", "B08C5T6Q3F", 8499, original=14995, discount=43.32, rating=4.4),
        _l("flipkart", "HOMGFHGZBHFGZAJ7", 8299, original=14995, discount=44.65, rating=4.4),
    ]),
    ("Philips HD9200 Air Fryer 0.8 kg Black", [
        _l("amazon", "B08L7QZ3K5", 7999, original=11995, discount=33.31, rating=4.3),
    ]),
    ("Mi Robot Vacuum-Mop 2 Pro+ Smart Cleaner", [
        _l("amazon", "B0B5MHX9SD", 27499, original=40999, discount=32.93, rating=4.2),
    ]),

    # ---- Beauty: Skincare ----------------------------------------------
    ("Cetaphil Gentle Skin Cleanser 250 ml for Dry to Normal Sensitive Skin", [
        _l("amazon", "B001E96L4Y", 499, original=735, discount=32.11, rating=4.6),
        _l("nykaa", "BTYZHFGZBHFGZAJ7", 489, original=735, discount=33.47, rating=4.5),
    ]),
    ("Cetaphil Gentle Skin Cleanser 500 ml for Dry to Normal Sensitive Skin", [
        _l("amazon", "B007VF13LO", 899, original=1295, discount=30.58, rating=4.6),
        _l("nykaa", "BTYZHFGZBHFGZBA7", 879, original=1295, discount=32.12, rating=4.6),
    ]),
    ("Mamaearth Vitamin C Face Wash with Vitamin C and Turmeric for Skin Illumination", [
        _l("nykaa", "BTYZHFGFBHFGZAJ7", 249, original=299, discount=16.72, rating=4.4),
        _l("amazon", "B07RFD5Y14", 269, original=299, discount=10.03, rating=4.3),
    ]),
    ("Plum Green Tea Pore Cleansing Face Wash with Glycolic Acid", [
        _l("nykaa", "BTYGZHFGFBHFGZA7", 345, original=395, discount=12.66, rating=4.4),
    ]),
    ("Plum Green Tea Alcohol-Free Toner with Witch Hazel for Acne-Prone Skin", [
        _l("nykaa", "BTYGZHFGFBHFGZA8", 390, original=450, discount=13.33, rating=4.5),
        _l("amazon", "B07F8XRFJN", 405, original=450, discount=10.00, rating=4.4),
    ]),
    ("The Ordinary Niacinamide 10% + Zinc 1% High-Strength Vitamin and Mineral Blemish Formula 30 ml", [
        _l("nykaa", "BTYGFHGZBHFGZAJ7", 590, original=750, discount=21.33, rating=4.5),
        _l("amazon", "B074W4FNB1", 650, original=750, discount=13.33, rating=4.4),
    ]),
    ("Minimalist 10% Niacinamide Face Serum For Acne Marks Blemishes & Oil Balancing", [
        _l("nykaa", "BTYHGZBHFGZAJ7Q", 599, original=699, discount=14.31, rating=4.4),
        _l("amazon", "B08FBJZG4M", 645, original=699, discount=7.72, rating=4.4),
    ]),
    ("Neutrogena Hydro Boost Water Gel Hyaluronic Acid Moisturiser 50 g", [
        _l("nykaa", "BTYZHFGFBHFGZAQ7", 800, original=950, discount=15.79, rating=4.5),
        _l("amazon", "B00AN9KKEO", 825, original=950, discount=13.16, rating=4.5),
    ]),
    ("Cetaphil Moisturising Lotion for Face & Body Dry to Normal Sensitive Skin 250 ml", [
        _l("amazon", "B0010ZBORW", 645, original=850, discount=24.12, rating=4.6),
        _l("nykaa", "BTYZHFGFBHFGZAQ8", 635, original=850, discount=25.29, rating=4.5),
    ]),
    ("La Roche-Posay Effaclar Duo (+) Anti-Acne Treatment Cream 40 ml", [
        _l("nykaa", "BTYZHFGFBHFGZAQ9", 1750, original=1990, discount=12.06, rating=4.4),
    ]),

    # ---- Beauty: Makeup ------------------------------------------------
    ("Lakme Absolute 3D Smooth Matte Foundation Honey Beige 25 g", [
        _l("amazon", "B07TF4P6ND", 1199, original=1500, discount=20.07, rating=4.2),
        _l("nykaa", "BTYZHFGFBHFGZBA0", 1149, original=1500, discount=23.40, rating=4.2),
    ]),
    ("Maybelline New York Fit Me Matte + Poreless Liquid Foundation 220", [
        _l("amazon", "B01N2ZTHC8", 549, original=799, discount=31.29, rating=4.3),
        _l("nykaa", "BTYZHFGFBHFGZBA1", 525, original=799, discount=34.29, rating=4.3),
    ]),
    ("MAC Ruby Woo Lipstick Retro Matte 3 g", [
        _l("nykaa", "BTYZHFGFBHFGZBA2", 2050, original=2050, rating=4.6),
    ]),
    ("Nykaa Matte to Last Liquid Lipstick Saudi 11 ml", [
        _l("nykaa", "BTYZHFGFBHFGZBA3", 425, original=550, discount=22.73, rating=4.3),
    ]),
    ("Sugar Cosmetics Smudge Me Not Liquid Lipstick 25 Pinky Promise", [
        _l("nykaa", "BTYZHFGFBHFGZBA4", 499, original=599, discount=16.69, rating=4.4),
        _l("amazon", "B07P55XRKP", 525, original=599, discount=12.35, rating=4.3),
    ]),

    # ---- Beauty: Haircare ----------------------------------------------
    ("L'Oreal Paris Hyaluron Moisture 72H Moisture Filling Shampoo 340 ml", [
        _l("nykaa", "BTYZHFGFBHFGZBA5", 449, original=549, discount=18.21, rating=4.4),
        _l("amazon", "B0BFKK6KK1", 469, original=549, discount=14.57, rating=4.4),
    ]),
    ("WOW Skin Science Apple Cider Vinegar Shampoo 300 ml", [
        _l("amazon", "B07Q21S7BC", 379, original=499, discount=24.05, rating=4.3),
        _l("nykaa", "BTYZHFGFBHFGZBA6", 369, original=499, discount=26.05, rating=4.3),
    ]),
    ("Mamaearth Onion Hair Oil for Hair Growth and Hair Fall Control 250 ml", [
        _l("nykaa", "BTYZHFGFBHFGZBA7", 549, original=599, discount=8.35, rating=4.3),
        _l("amazon", "B07KTRFLR7", 569, original=599, discount=5.01, rating=4.3),
    ]),
    ("Dyson Supersonic Hair Dryer HD08 Iron Fuchsia", [
        _l("nykaa", "BTYZHFGFBHFGZBA8", 41900, original=41900, rating=4.7),
    ]),

    # ---- Fashion: Footwear ---------------------------------------------
    ("Nike Air Max SC Running Shoes for Men White / Black", [
        _l("amazon", "B08GS5ZPWC", 5497, original=6995, discount=21.42, rating=4.4),
        _l("flipkart", "FOTGZHFGFBHFGZAQ", 5295, original=6995, discount=24.30, rating=4.3),
    ]),
    ("Adidas Lite Racer Adapt 5.0 Slip-On Running Shoes", [
        _l("amazon", "B0BV6CVN3L", 3999, original=5999, discount=33.34, rating=4.3),
    ]),
    ("Puma Smash V2 Sneakers Black White", [
        _l("amazon", "B07JKFC8JP", 2249, original=3499, discount=35.72, rating=4.4),
        _l("flipkart", "FOTGZHFGFBHFGZAR", 2199, original=3499, discount=37.15, rating=4.4),
    ]),

    # ---- Sports & Fitness ----------------------------------------------
    ("AmazonBasics Yoga Mat 6 mm Premium Anti-Skid Blue", [
        _l("amazon", "B07T1NDS2K", 599, original=999, discount=40.04, rating=4.2),
    ]),
    ("Decathlon Domyos Adjustable Dumbbells Set 20 kg", [
        _l("amazon", "B08QX9KTPK", 5999, original=7999, discount=25.00, rating=4.5),
    ]),
    ("Yonex Mavis 200i Nylon Shuttlecock Pack of 6", [
        _l("amazon", "B00CECQEAS", 459, original=600, discount=23.50, rating=4.3),
        _l("flipkart", "SPTGZHFGFBHFGZAQ", 449, original=600, discount=25.17, rating=4.3),
    ]),

    # ---- Books & Stationery (small set, semantic recall edge case) -----
    ("Atomic Habits by James Clear — Tiny Changes Remarkable Results", [
        _l("amazon", "1847941834", 449, original=799, discount=43.81, rating=4.7),
        _l("flipkart", "BKSGZHFGFBHFGZAQ", 425, original=799, discount=46.81, rating=4.7),
    ]),
    ("The Psychology of Money by Morgan Housel", [
        _l("amazon", "9390166268", 299, original=399, discount=25.06, rating=4.6),
        _l("flipkart", "BKSGZHFGFBHFGZAR", 285, original=399, discount=28.57, rating=4.6),
    ]),
    ("Parker Vector Standard Roller Ball Pen Black Body", [
        _l("amazon", "B00FWEK20I", 220, original=275, discount=20.00, rating=4.3),
    ]),
]


def _to_scraped(canonical_title: str, listing: dict) -> ScrapedListing:
    return ScrapedListing(
        platform=listing["platform"],
        platform_product_id=listing["pid"],
        title=canonical_title,
        price=Decimal(str(listing["price"])),
        original_price=Decimal(str(listing["original"])) if listing.get("original") else None,
        discount=Decimal(str(listing["discount"])) if listing.get("discount") else None,
        rating=Decimal(str(listing["rating"])) if listing.get("rating") else None,
        url=listing.get("url") or f"https://{listing['platform']}.example.com/{listing['pid']}",
        image_url=listing.get("image"),
    )


def _grouped_by_platform(catalogue) -> dict[str, list[ScrapedListing]]:
    """upsert_listings expects all rows in a batch to share a platform —
    that's how the matcher decides whether to match into the existing
    canonical pool or spawn a new one. Group accordingly."""
    by_platform: dict[str, list[ScrapedListing]] = {}
    for canonical_title, listings in catalogue:
        for listing in listings:
            by_platform.setdefault(listing["platform"], []).append(
                _to_scraped(canonical_title, listing)
            )
    return by_platform


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed PromoSensei with the demo catalogue")
    parser.add_argument("--reset", action="store_true", help="Drop & recreate tables before seeding")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s — %(message)s")
    log = logging.getLogger("seed_demo")

    if args.reset:
        log.info("Dropping existing tables…")
        Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    by_platform = _grouped_by_platform(CATALOGUE)
    db = SessionLocal()
    try:
        # Amazon first establishes the canonical pool — Flipkart and Nykaa
        # then *match into* it instead of forking duplicate canonicals.
        platform_order = ("amazon", "flipkart", "nykaa")
        total_inserted = total_updated = 0
        for platform in platform_order:
            listings = by_platform.get(platform, [])
            if not listings:
                continue
            log.info("[%s] seeding %d listings", platform, len(listings))
            result = upsert_listings(db, listings, platform=platform)
            log.info(
                "[%s] inserted=%d updated=%d errors=%d",
                platform, result.inserted, result.updated, result.errors,
            )
            total_inserted += result.inserted
            total_updated += result.updated

        if total_inserted + total_updated == 0:
            log.error("No listings ingested.")
            return 1

        stats = reindex_products(db)
        log.info(
            "Index: model=%s embedded=%d refreshed=%d skipped=%d",
            stats.model_id, stats.embedded, stats.refreshed, stats.skipped,
        )
    finally:
        db.close()

    log.info(
        "Demo seed complete — %d catalogue entries → inserted=%d updated=%d.",
        len(CATALOGUE), total_inserted, total_updated,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
