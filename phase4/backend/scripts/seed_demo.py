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
import urllib.parse
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

    # ---- Books & Stationery -------------------------------------------
    ("Atomic Habits by James Clear — Tiny Changes Remarkable Results", [
        _l("amazon", "1847941834", 449, original=799, discount=43.81, rating=4.7),
        _l("flipkart", "BKSGZHFGFBHFGZAQ", 425, original=799, discount=46.81, rating=4.7),
    ]),
    ("The Psychology of Money by Morgan Housel", [
        _l("amazon", "9390166268", 299, original=399, discount=25.06, rating=4.6),
        _l("flipkart", "BKSGZHFGFBHFGZAR", 285, original=399, discount=28.57, rating=4.6),
    ]),
    ("Sapiens A Brief History of Humankind by Yuval Noah Harari", [
        _l("amazon", "0099590085", 399, original=599, discount=33.39, rating=4.6),
    ]),
    ("Ikigai The Japanese Secret to a Long and Happy Life", [
        _l("amazon", "1786330385", 199, original=399, discount=50.13, rating=4.5),
        _l("flipkart", "BKSGZHFGFBHFGZAS", 189, original=399, discount=52.63, rating=4.5),
    ]),
    ("Rich Dad Poor Dad by Robert T. Kiyosaki", [
        _l("amazon", "1612680194", 269, original=399, discount=32.58, rating=4.6),
    ]),
    ("Parker Vector Standard Roller Ball Pen Black Body", [
        _l("amazon", "B00FWEK20I", 220, original=275, discount=20.00, rating=4.3),
    ]),

    # ---- Phones (extended) ---------------------------------------------
    ("Realme Narzo 60 Pro 5G (256 GB) Cosmic Black", [
        _l("amazon", "B0C9R55C3K", 23999, original=29999, discount=20.00, rating=4.3),
        _l("flipkart", "MOBGZNRZ60PRO5G", 22999, original=29999, discount=23.34, rating=4.3),
    ]),
    ("Vivo Y200 5G (128 GB) Glitter Aqua", [
        _l("flipkart", "MOBGZVIVOY200", 21999, original=24999, discount=12.00, rating=4.2),
    ]),
    ("Oppo Reno 11 Pro 5G (256 GB) Pearl White", [
        _l("amazon", "B0CV5W6JLF", 39999, original=44999, discount=11.11, rating=4.3),
        _l("flipkart", "MOBGZOPPORENO11", 38999, original=44999, discount=13.33, rating=4.3),
    ]),
    ("iQOO Neo 9 Pro 5G (128 GB) Fiery Red", [
        _l("amazon", "B0CSG8YV6X", 32999, original=36999, discount=10.81, rating=4.4),
        _l("flipkart", "MOBGZIQOONEO9PRO", 31999, original=36999, discount=13.51, rating=4.4),
    ]),
    ("Nothing Phone 2a (256 GB) Milk", [
        _l("flipkart", "MOBGZNOTHING2A", 27999, original=29999, discount=6.67, rating=4.3),
    ]),

    # ---- Tablets -------------------------------------------------------
    ("Apple iPad Air 11-inch M2 Wi-Fi 128 GB Space Gray", [
        _l("amazon", "B0CWN3GY1M", 59900, original=59900, rating=4.7),
        _l("flipkart", "TABGZIPADAIRM2", 58999, original=59900, discount=1.50, rating=4.7),
    ]),
    ("Samsung Galaxy Tab S9 FE 5G 10.9-inch Tablet 128 GB Mint", [
        _l("amazon", "B0CGM8KKJZ", 41999, original=51999, discount=19.23, rating=4.4),
        _l("flipkart", "TABGZGALAXYTABS9FE", 40999, original=51999, discount=21.16, rating=4.4),
    ]),
    ("Lenovo Tab M11 11-inch FHD Tablet 128 GB Luna Grey", [
        _l("amazon", "B0CSS9JVDC", 18499, original=23999, discount=22.92, rating=4.2),
    ]),

    # ---- Gaming --------------------------------------------------------
    ("Sony PlayStation 5 Slim Console with Disc Drive", [
        _l("amazon", "B0CL61F39H", 54990, original=54990, rating=4.7),
        _l("flipkart", "GAMGZPS5SLIM", 53999, original=54990, discount=1.80, rating=4.7),
    ]),
    ("Xbox Series S 512 GB Console White", [
        _l("amazon", "B08G9J44ZK", 34990, original=37990, discount=7.90, rating=4.6),
    ]),
    ("Sony DualSense Wireless Controller for PS5 Midnight Black", [
        _l("amazon", "B099GG93WD", 5499, original=6390, discount=13.94, rating=4.6),
        _l("flipkart", "GAMGZDUALSENSE", 5390, original=6390, discount=15.65, rating=4.6),
    ]),
    ("HyperX Cloud Stinger 2 Gaming Headset 7.1 Surround Sound", [
        _l("amazon", "B0BGGW3VFP", 3490, original=4999, discount=30.19, rating=4.5),
    ]),
    ("Logitech G502 X Plus Lightspeed Wireless Gaming Mouse", [
        _l("amazon", "B0B6PRTQGT", 12995, original=17995, discount=27.79, rating=4.6),
    ]),

    # ---- Cameras -------------------------------------------------------
    ("GoPro HERO12 Black 5.3K60 Action Camera", [
        _l("amazon", "B0CCWFMWY1", 38990, original=49500, discount=21.23, rating=4.5),
        _l("flipkart", "CAMGZGOPROHERO12", 37990, original=49500, discount=23.25, rating=4.5),
    ]),
    ("Canon EOS R50 24.2MP Mirrorless Camera with RF-S 18-45mm Lens", [
        _l("amazon", "B0BVQTHTTV", 67990, original=74995, discount=9.34, rating=4.7),
    ]),
    ("Sony Alpha ZV-E10 Mirrorless Vlog Camera with 16-50mm Lens", [
        _l("amazon", "B098JZSC8V", 64990, original=78990, discount=17.72, rating=4.6),
        _l("flipkart", "CAMGZSONYZVE10", 63990, original=78990, discount=18.99, rating=4.6),
    ]),

    # ---- Kitchen Appliances --------------------------------------------
    ("Prestige Iris 750W Mixer Grinder with 3 Stainless Steel Jars", [
        _l("amazon", "B07BHFW9QQ", 2999, original=4895, discount=38.73, rating=4.3),
        _l("flipkart", "HOMGZPRESTIGEMIXER", 2899, original=4895, discount=40.78, rating=4.3),
    ]),
    ("Bajaj Majesty 1603 TSS 16-Litre Oven Toaster Griller", [
        _l("amazon", "B00LD5VRGE", 6499, original=8995, discount=27.75, rating=4.2),
    ]),
    ("Pigeon by Stovekraft Kettle 1.5L Stainless Steel Electric", [
        _l("amazon", "B00ZW8QLSA", 599, original=1295, discount=53.75, rating=4.2),
    ]),
    ("Eureka Forbes Vacuum Cleaner Forbes Trendy Zip 1000W", [
        _l("amazon", "B07BJX1KZV", 4799, original=6995, discount=31.39, rating=4.1),
    ]),

    # ---- More Skincare -------------------------------------------------
    ("Dot & Key Vitamin C+E Sorbet Sunscreen SPF 50 PA+++ 50 ml", [
        _l("nykaa", "BTYZHFGFBHFGZBB1", 525, original=695, discount=24.46, rating=4.5),
        _l("amazon", "B09VGPTW8D", 549, original=695, discount=21.01, rating=4.4),
    ]),
    ("Foxtale Daily Sunscreen SPF 50 PA+++ Lightweight 50 ml", [
        _l("nykaa", "BTYZHFGFBHFGZBB2", 449, original=549, discount=18.21, rating=4.5),
    ]),
    ("Olay Total Effects 7 in 1 Anti-Ageing Day Cream 50 g", [
        _l("nykaa", "BTYZHFGFBHFGZBB3", 999, original=1199, discount=16.68, rating=4.4),
        _l("amazon", "B00JBIN9OC", 1049, original=1199, discount=12.51, rating=4.4),
    ]),
    ("Pilgrim Korean Pep-Start C-Glow Vitamin C Face Serum 30 ml", [
        _l("nykaa", "BTYZHFGFBHFGZBB4", 595, original=795, discount=25.16, rating=4.4),
    ]),
    ("CeraVe Moisturising Cream for Dry to Very Dry Skin 340 g", [
        _l("nykaa", "BTYZHFGFBHFGZBB5", 1599, original=1999, discount=20.01, rating=4.6),
        _l("amazon", "B00TTD9BRC", 1649, original=1999, discount=17.51, rating=4.6),
    ]),

    # ---- Perfumes ------------------------------------------------------
    ("Skinn by Titan Celeste Eau de Parfum for Women 50 ml", [
        _l("nykaa", "BTYZHFGFBHFGZBB6", 1395, original=1700, discount=17.94, rating=4.5),
        _l("amazon", "B07HRY5DVQ", 1450, original=1700, discount=14.71, rating=4.4),
    ]),
    ("Calvin Klein CK One Eau de Toilette Unisex 100 ml", [
        _l("nykaa", "BTYZHFGFBHFGZBB7", 4599, original=6500, discount=29.25, rating=4.6),
    ]),
    ("Bvlgari Aqva Pour Homme Eau de Toilette for Men 100 ml", [
        _l("nykaa", "BTYZHFGFBHFGZBB8", 6999, original=7800, discount=10.27, rating=4.7),
    ]),
    ("Engage Mate Perfume Spray for Men No Gas Deodorant 120 ml", [
        _l("amazon", "B07S35KZN3", 230, original=350, discount=34.29, rating=4.3),
    ]),

    # ---- More Hair / Body ----------------------------------------------
    ("Schwarzkopf Bonacure Moisture Kick Shampoo 250 ml", [
        _l("nykaa", "BTYZHFGFBHFGZBB9", 749, original=895, discount=16.31, rating=4.5),
    ]),
    ("Philips BHD308/30 Hair Dryer 1600W with ThermoProtect", [
        _l("amazon", "B0779VNGGF", 1349, original=1995, discount=32.38, rating=4.3),
        _l("flipkart", "ACCGZPHILIPSBHD", 1299, original=1995, discount=34.89, rating=4.3),
    ]),
    ("Dove Cream Beauty Bathing Soap 100g Pack of 6", [
        _l("amazon", "B07Z8SRNT5", 295, original=378, discount=21.96, rating=4.5),
    ]),

    # ---- More Fashion --------------------------------------------------
    ("Levi's Men 511 Slim Fit Jeans Stretchable Mid-Rise Blue", [
        _l("amazon", "B07T5GJ5KC", 1799, original=3499, discount=48.59, rating=4.3),
        _l("flipkart", "FOTGZLEVIS511", 1699, original=3499, discount=51.44, rating=4.3),
    ]),
    ("US Polo Assn. Men Solid Regular Fit Polo T-Shirt Navy", [
        _l("amazon", "B0BVVH6L77", 899, original=1499, discount=40.03, rating=4.3),
        _l("flipkart", "FOTGZUSPOLOTSHIRT", 849, original=1499, discount=43.36, rating=4.3),
    ]),
    ("Wildcraft Hypadura Plus 35L Laptop Backpack Black", [
        _l("amazon", "B07Z6F3J5R", 1499, original=2599, discount=42.32, rating=4.4),
        _l("flipkart", "FOTGZWILDCRAFTBKPK", 1399, original=2599, discount=46.17, rating=4.4),
    ]),
    ("Fastrack Reflex Vox 2.0 Smartwatch Black", [
        _l("amazon", "B0CHV5PZ8D", 2495, original=3995, discount=37.55, rating=4.1),
    ]),
    ("Fossil Gen 6 Smartwatch Black Stainless Steel 44mm", [
        _l("amazon", "B09KRL36SD", 19995, original=23995, discount=16.67, rating=4.4),
    ]),
    ("Adidas Originals Stan Smith Sneakers White Green", [
        _l("amazon", "B07F61CFGG", 5999, original=8999, discount=33.34, rating=4.5),
        _l("flipkart", "FOTGZADIDASSTANSMITH", 5799, original=8999, discount=35.56, rating=4.5),
    ]),

    # ---- More Sports ---------------------------------------------------
    ("Nivia Storm Football Size 5 Hand Stitched Synthetic", [
        _l("amazon", "B07PJ7NWVB", 599, original=999, discount=40.04, rating=4.4),
    ]),
    ("Cosco Cricket Bat English Willow Short Handle", [
        _l("amazon", "B07J2D5L3T", 1999, original=2999, discount=33.34, rating=4.2),
    ]),
    ("AmazonBasics Resistance Bands Set with Handles 5-Pack", [
        _l("amazon", "B01BXYMD9Y", 999, original=1799, discount=44.47, rating=4.3),
    ]),

    # ---- TV & Home (extended) ------------------------------------------
    ("Samsung 55-inch Crystal 4K UHD Smart TV UA55CUE60AKLXL", [
        _l("amazon", "B0C8MZ4GFK", 39990, original=58900, discount=32.10, rating=4.4),
        _l("flipkart", "TVSGZSAMSUNG55CUE60", 38990, original=58900, discount=33.80, rating=4.4),
    ]),
    ("LG 1.5 Ton 5 Star Inverter Split AC PS-Q19YNZE Copper", [
        _l("amazon", "B0BSJSWMJ5", 41990, original=63490, discount=33.86, rating=4.5),
    ]),
    ("Voltas Beko 8 kg Top Load Fully Automatic Washing Machine", [
        _l("flipkart", "WMGZVOLTASBEKO8KG", 18990, original=28990, discount=34.49, rating=4.2),
    ]),
    ("Whirlpool 240L 2 Star Frost-Free Double Door Refrigerator", [
        _l("amazon", "B0BR5L2J67", 23990, original=33490, discount=28.37, rating=4.3),
    ]),

    # ---- Audio (extended) ----------------------------------------------
    ("Bose QuietComfort Ultra Wireless Noise Cancelling Headphones", [
        _l("amazon", "B0CCYZWDDB", 39990, original=44990, discount=11.11, rating=4.6),
    ]),
    ("Apple AirPods Max Over-Ear Headphones Sky Blue", [
        _l("amazon", "B08PZHNMDR", 51900, original=59900, discount=13.36, rating=4.6),
    ]),
    ("OnePlus Buds 3 True Wireless Earphones Splendid Blue", [
        _l("amazon", "B0CWPFJZBL", 4999, original=5499, discount=9.09, rating=4.3),
        _l("flipkart", "ACCGZONEPLUSBUDS3", 4799, original=5499, discount=12.73, rating=4.3),
    ]),
    ("realme Buds Air 5 Pro True Wireless Earphones Astral Black", [
        _l("flipkart", "ACCGZREALMEBUDSAIR5", 3999, original=5999, discount=33.34, rating=4.3),
    ]),

    # ---- Men's Clothing ------------------------------------------------
    ("Allen Solly Men Solid Polo Neck T-Shirt Navy Blue Cotton", [
        _l("amazon", "B07DFLG2NN", 599, original=1299, discount=53.89, rating=4.3),
        _l("flipkart", "FOTGZALLENSOLLYPOLO", 549, original=1299, discount=57.74, rating=4.3),
    ]),
    ("Roadster Men Pure Cotton Round Neck T-Shirt Olive Green", [
        _l("flipkart", "FOTGZROADSTERTEE", 399, original=899, discount=55.62, rating=4.2),
    ]),
    ("Peter England Men Slim Fit Formal Shirt White Cotton Full Sleeves", [
        _l("amazon", "B0CGJDDCCN", 999, original=1999, discount=50.03, rating=4.4),
        _l("flipkart", "FOTGZPETERENGLAND", 949, original=1999, discount=52.53, rating=4.4),
    ]),
    ("Van Heusen Men Premium Slim Fit Formal Shirt Light Blue", [
        _l("amazon", "B07KX7CL82", 1299, original=2499, discount=48.02, rating=4.3),
    ]),
    ("Jack & Jones Men Slim Fit Mid-Rise Stretch Jeans Dark Indigo", [
        _l("amazon", "B0BRFNBM3K", 1999, original=3499, discount=42.87, rating=4.4),
        _l("flipkart", "FOTGZJACKJONESJEANS", 1899, original=3499, discount=45.73, rating=4.4),
    ]),
    ("Wrangler Men Skanders Slim Fit Jeans Stretchable Mid Blue", [
        _l("amazon", "B07GTCTJG7", 1799, original=2999, discount=40.01, rating=4.3),
    ]),
    ("Pepe Jeans Men Slim Fit Mid-Rise Cropped Jeans Black Wash", [
        _l("flipkart", "FOTGZPEPEJEANS", 1999, original=3499, discount=42.87, rating=4.3),
    ]),
    ("U.S. Polo Assn. Men Solid Pure Cotton Round Neck T-Shirt Pack of 3", [
        _l("amazon", "B0BVVH6PK3", 1499, original=2999, discount=50.02, rating=4.3),
    ]),
    ("HRX by Hrithik Roshan Men Active Dryfit Sports T-Shirt Black", [
        _l("amazon", "B0CKJ8JZ3W", 549, original=999, discount=45.05, rating=4.2),
        _l("flipkart", "FOTGZHRXTEE", 499, original=999, discount=50.05, rating=4.2),
    ]),
    ("Puma Men Essentials Logo Hoodie Cotton Blend Black", [
        _l("amazon", "B09M3D8V4F", 1599, original=2999, discount=46.68, rating=4.4),
        _l("flipkart", "FOTGZPUMAHOODIE", 1499, original=2999, discount=50.02, rating=4.4),
    ]),
    ("Adidas Men Originals Trefoil Hoodie Cotton Black White", [
        _l("amazon", "B07BBL5CBZ", 2799, original=3999, discount=30.01, rating=4.5),
    ]),
    ("Nike Sportswear Club Fleece Pullover Hoodie Men Charcoal", [
        _l("amazon", "B07W6QMWG7", 2495, original=3495, discount=28.61, rating=4.5),
    ]),
    ("Levi's Men Standard Fit Trucker Denim Jacket Dark Blue", [
        _l("amazon", "B00R36Y9ZW", 3499, original=5999, discount=41.67, rating=4.4),
    ]),
    ("Highlander Men Slim Fit Casual Solid Cotton Shirt Maroon", [
        _l("flipkart", "FOTGZHIGHLANDER", 549, original=1499, discount=63.38, rating=4.1),
    ]),
    ("Jockey Men's Cotton Briefs Pack of 3 Assorted Colours", [
        _l("amazon", "B074GG7G36", 549, original=695, discount=21.01, rating=4.5),
        _l("flipkart", "FOTGZJOCKEYBRIEFS", 519, original=695, discount=25.32, rating=4.5),
    ]),
    ("Nike Men Dri-FIT Running Shorts 7-inch Black", [
        _l("amazon", "B07PQHJ4LB", 1495, original=1995, discount=25.06, rating=4.4),
    ]),
    ("Adidas Men Track Pants Tiro 23 Slim Fit Black", [
        _l("flipkart", "FOTGZADIDASTIRO", 1799, original=2999, discount=40.01, rating=4.4),
    ]),

    # ---- Women's Clothing ----------------------------------------------
    ("ONLY Women Floral Print A-Line Mini Dress Sleeveless Pink", [
        _l("amazon", "B0CK1CG2VG", 1299, original=2499, discount=48.02, rating=4.3),
        _l("flipkart", "FOTGZONLYDRESS", 1199, original=2499, discount=52.02, rating=4.3),
    ]),
    ("Vero Moda Women Black Solid Sheath Knee-Length Dress", [
        _l("amazon", "B0CRT6KQXV", 1499, original=2599, discount=42.32, rating=4.3),
    ]),
    ("Biba Women Pink Floral Anarkali Kurta with Dupatta Set", [
        _l("amazon", "B0CG75WM4B", 1799, original=3299, discount=45.47, rating=4.4),
        _l("flipkart", "FOTGZBIBAANARKALI", 1699, original=3299, discount=48.50, rating=4.4),
    ]),
    ("W for Woman Embroidered Straight Cotton Kurta Mustard Yellow", [
        _l("amazon", "B0BS7YQHR2", 1299, original=2199, discount=40.93, rating=4.3),
    ]),
    ("Libas Women Floral Print Cotton Anarkali Kurta with Trousers", [
        _l("flipkart", "FOTGZLIBASKURTA", 1499, original=2999, discount=50.02, rating=4.3),
    ]),
    ("Mitera Women Pink Banarasi Silk Saree with Zari Border", [
        _l("flipkart", "FOTGZMITERASAREE", 1299, original=4999, discount=74.01, rating=4.3),
    ]),
    ("Janasya Women Yellow Floral Printed Cotton Kurti", [
        _l("amazon", "B0BHN3W3CW", 599, original=1599, discount=62.54, rating=4.2),
    ]),
    ("H&M Women Cotton Cropped T-Shirt White Round Neck", [
        _l("flipkart", "FOTGZHMTEE", 499, original=799, discount=37.55, rating=4.2),
    ]),
    ("Forever 21 Women Boyfriend Fit Distressed Mom Jeans Light Wash", [
        _l("flipkart", "FOTGZFOREVER21JEANS", 1499, original=2899, discount=48.29, rating=4.2),
    ]),
    ("Levi's Women 711 Skinny Jeans Mid-Rise Stretchable Indigo", [
        _l("amazon", "B07TVDDP62", 2199, original=3999, discount=45.01, rating=4.4),
    ]),
    ("Zara Women Oversized Knit Sweater Cream Round Neck", [
        _l("flipkart", "FOTGZZARASWEATER", 2490, original=3490, discount=28.65, rating=4.4),
    ]),
    ("Zivame Women Seamless Wirefree T-Shirt Bra Beige", [
        _l("amazon", "B09VDSY3R4", 595, original=995, discount=40.20, rating=4.4),
        _l("nykaa", "BTYZHFGFBHFGZBC1", 549, original=995, discount=44.82, rating=4.4),
    ]),
    ("Clovia Women Cotton Mid-Waist Hipster Panties Pack of 3", [
        _l("amazon", "B0BNTHV9X3", 449, original=999, discount=55.06, rating=4.3),
    ]),
    ("ONLY Women Wide-Leg High-Waist Trousers Beige Tailored", [
        _l("flipkart", "FOTGZONLYTROUSERS", 1599, original=2999, discount=46.68, rating=4.3),
    ]),
    ("Anouk Women Printed Co-Ord Set Crop Top with Palazzo", [
        _l("flipkart", "FOTGZANOUKCOORDS", 1099, original=2499, discount=56.02, rating=4.2),
    ]),

    # ---- Footwear (Extended) -------------------------------------------
    ("Crocs Classic Clog Unisex Black Slip-On", [
        _l("amazon", "B017JG1GE4", 2495, original=3495, discount=28.61, rating=4.6),
        _l("flipkart", "FOTGZCROCSCLOG", 2395, original=3495, discount=31.47, rating=4.6),
    ]),
    ("Bata Men Office Formal Lace-Up Leather Shoes Brown", [
        _l("amazon", "B07YHRT8X1", 1799, original=2499, discount=28.01, rating=4.3),
    ]),
    ("Sparx Men Running Sports Shoes Black Lightweight Mesh", [
        _l("amazon", "B0CJDB7M9F", 999, original=1899, discount=47.39, rating=4.2),
        _l("flipkart", "FOTGZSPARXRUN", 949, original=1899, discount=50.03, rating=4.2),
    ]),
    ("Skechers Go Walk 6 Men's Walking Shoes Slip-On Black", [
        _l("amazon", "B0BCD45MRB", 4999, original=6999, discount=28.58, rating=4.6),
    ]),
    ("Asics Gel-Excite 10 Men Running Shoes Cushioned Blue", [
        _l("amazon", "B0BWDVH75M", 4799, original=6499, discount=26.16, rating=4.5),
    ]),
    ("Hush Puppies Women Loafers Black Leather Slip-On Casual", [
        _l("amazon", "B07RMC9R64", 2299, original=3499, discount=34.30, rating=4.3),
    ]),
    ("Metro Women Block Heel Sandals Black Open Toe Party Wear", [
        _l("flipkart", "FOTGZMETROHEELS", 999, original=1999, discount=50.03, rating=4.2),
    ]),
    ("Woodland Men's Genuine Leather Outdoor Boots Camel Brown", [
        _l("amazon", "B07DG39CG5", 3499, original=5495, discount=36.32, rating=4.5),
    ]),

    # ---- Bags & Luggage ------------------------------------------------
    ("American Tourister Hugo 32-Inch Polycarbonate Hard Trolley Suitcase", [
        _l("amazon", "B0BS1SR1PT", 4999, original=10500, discount=52.39, rating=4.5),
        _l("flipkart", "FOTGZAMTOURISTERTRL", 4799, original=10500, discount=54.30, rating=4.5),
    ]),
    ("Skybags Verge Strolly 55cm Polycarbonate Cabin Suitcase Black", [
        _l("amazon", "B09KGL3T4J", 2999, original=8200, discount=63.43, rating=4.4),
    ]),
    ("Wildcraft Voyager Plus 65L Rucksack Backpack Trekking", [
        _l("amazon", "B07VPV81Y6", 2499, original=3999, discount=37.51, rating=4.5),
    ]),
    ("Caprese Women Mini Bea Tote Handbag PU Leather Pink", [
        _l("amazon", "B0CW1HT7HF", 1349, original=2495, discount=45.93, rating=4.3),
        _l("flipkart", "FOTGZCAPRESETOTE", 1299, original=2495, discount=47.94, rating=4.3),
    ]),
    ("Lavie Women Leather Crossbody Sling Bag Tan", [
        _l("amazon", "B0BLZ1KH8M", 1599, original=2999, discount=46.68, rating=4.3),
    ]),
    ("Tommy Hilfiger Men Leather Bifold Wallet Brown", [
        _l("amazon", "B07R6NXLQR", 1799, original=2499, discount=28.01, rating=4.5),
    ]),

    # ---- Trending Electronics ------------------------------------------
    ("DJI Mini 4 Pro Camera Drone with RC 2 Remote 4K HDR Video", [
        _l("amazon", "B0CGV35BFM", 95900, original=99900, discount=4.00, rating=4.7),
    ]),
    ("DJI Osmo Pocket 3 Creator Combo 4K Vlog Camera", [
        _l("amazon", "B0CHX5WFMW", 71900, original=74900, discount=4.01, rating=4.7),
    ]),
    ("Insta360 X3 360 Action Camera 5.7K Waterproof", [
        _l("amazon", "B0BFZHHQH9", 39990, original=49990, discount=20.00, rating=4.6),
    ]),
    ("Apple Vision Pro Successor Mixed Reality Headset 256GB", [
        _l("amazon", "B0CSHH2X6F", 339900, original=339900, rating=4.4),
    ]),
    ("Meta Quest 3 128GB All-in-One VR Headset", [
        _l("amazon", "B0CCMG2TR8", 49990, original=53990, discount=7.41, rating=4.6),
    ]),
    ("Anker Soundcore Liberty 4 NC Wireless Earbuds Active Noise Cancellation", [
        _l("amazon", "B0CC8YV1BS", 7999, original=9999, discount=20.00, rating=4.5),
        _l("flipkart", "ACCGZSOUNDCORE4NC", 7799, original=9999, discount=22.00, rating=4.5),
    ]),
    ("Bose SoundLink Flex Bluetooth Portable Speaker Stone Blue", [
        _l("amazon", "B09GXR4P9F", 14900, original=17900, discount=16.76, rating=4.7),
    ]),
    ("Apple Pencil USB-C 2nd Generation for iPad", [
        _l("amazon", "B0CG65Z3JH", 8999, original=8999, rating=4.7),
    ]),
    ("Logitech MX Anywhere 3S Wireless Compact Mouse Pale Grey", [
        _l("amazon", "B0CGN8KBYZ", 7995, original=8995, discount=11.12, rating=4.6),
    ]),
    ("Razer BlackWidow V4 Pro Mechanical Gaming Keyboard RGB", [
        _l("amazon", "B0BS6WZP92", 24999, original=29999, discount=16.67, rating=4.5),
    ]),
    ("ASUS ROG Strix G16 Gaming Laptop Intel i7 14th Gen RTX 4060", [
        _l("amazon", "B0CWPFCBLW", 134990, original=159990, discount=15.63, rating=4.5),
        _l("flipkart", "COMGZASUSROGSTRIX", 132990, original=159990, discount=16.88, rating=4.5),
    ]),
    ("Acer Predator Helios Neo 16 RTX 4070 Gaming Laptop i7-13700HX", [
        _l("amazon", "B0CSGSZSPX", 149990, original=174990, discount=14.29, rating=4.4),
    ]),
    ("Apple MacBook Pro 14-inch M3 Pro Chip 18GB / 512GB Space Black", [
        _l("amazon", "B0CM5HC3F4", 199900, original=229900, discount=13.05, rating=4.8),
        _l("flipkart", "COMGZMACBOOKPROM3", 197900, original=229900, discount=13.92, rating=4.8),
    ]),
    ("LG UltraGear 27-inch QHD Nano IPS 240Hz Gaming Monitor 27GP850", [
        _l("amazon", "B095RJ9NQR", 35990, original=49999, discount=28.02, rating=4.6),
    ]),
    ("Sony Bravia 65-inch 4K Ultra HD Smart Google TV X80L Series", [
        _l("amazon", "B0CCRLY7NB", 79990, original=109900, discount=27.22, rating=4.5),
        _l("flipkart", "TVSGZSONYBRAVIA65", 78990, original=109900, discount=28.13, rating=4.5),
    ]),
    ("Samsung Neo QLED 55-inch 4K Smart TV QN90D Quantum HDR+", [
        _l("amazon", "B0D2CXMC86", 149990, original=199900, discount=24.97, rating=4.6),
    ]),
    ("Amazon Echo Dot 5th Gen Smart Speaker with Alexa Charcoal", [
        _l("amazon", "B09B8Z7JNJ", 4499, original=5499, discount=18.18, rating=4.4),
    ]),
    ("Google Nest Hub 2nd Gen 7-inch Smart Display Charcoal", [
        _l("amazon", "B08LSQ49DB", 7999, original=9999, discount=20.00, rating=4.5),
    ]),
    ("Apple HomePod Mini Smart Speaker Space Gray", [
        _l("amazon", "B08PV6L8GX", 9900, original=10900, discount=9.17, rating=4.5),
    ]),
    ("Mi 360 Home Security Camera 2K Pro Wi-Fi Indoor", [
        _l("amazon", "B09VKVNB9G", 3499, original=4999, discount=30.01, rating=4.3),
    ]),

    # ---- More Phones (Trending) ----------------------------------------
    ("Samsung Galaxy S24 5G (256 GB) Onyx Black", [
        _l("amazon", "B0CSL31WK4", 79999, original=89999, discount=11.11, rating=4.6),
        _l("flipkart", "MOBGZSAMSUNGS24", 78999, original=89999, discount=12.22, rating=4.5),
    ]),
    ("Samsung Galaxy Z Flip 5 5G (256 GB) Mint", [
        _l("amazon", "B0C6F1SCSR", 89999, original=109999, discount=18.18, rating=4.4),
    ]),
    ("Samsung Galaxy Z Fold 5 5G (512 GB) Phantom Black", [
        _l("amazon", "B0C6F1Y8MZ", 154999, original=174999, discount=11.43, rating=4.5),
    ]),
    ("OnePlus 12 5G (16 GB / 256 GB) Silky Black", [
        _l("amazon", "B0CSGNRDPK", 64999, original=69999, discount=7.14, rating=4.5),
    ]),
    ("Xiaomi 14 5G (256 GB) Jade Green", [
        _l("flipkart", "MOBGZXIAOMI14", 54999, original=69999, discount=21.43, rating=4.4),
    ]),
    ("Apple iPhone 14 (128 GB) Midnight", [
        _l("amazon", "B0BDJ7C6GP", 56999, original=69900, discount=18.46, rating=4.6),
        _l("flipkart", "MOBGZIPHONE14", 55999, original=69900, discount=19.89, rating=4.6),
    ]),
    ("Apple iPhone 13 (128 GB) Starlight", [
        _l("amazon", "B09G99CW2N", 47999, original=59900, discount=19.89, rating=4.7),
    ]),
    ("Motorola Edge 50 Pro 5G (256 GB) Vegan Leather Caneel Bay", [
        _l("amazon", "B0CW2XJWBL", 27999, original=33999, discount=17.65, rating=4.3),
    ]),
    ("Honor X9b 5G (256 GB) Midnight Black 108MP Camera", [
        _l("flipkart", "MOBGZHONORX9B", 22999, original=27999, discount=17.86, rating=4.3),
    ]),

    # ---- Watches (Luxury / Casual) -------------------------------------
    ("Casio Edifice Men's Chronograph Stainless Steel Watch", [
        _l("amazon", "B07PB4GTLV", 8995, original=12995, discount=30.78, rating=4.5),
    ]),
    ("Titan Raga Women's Analog Rose Gold Tone Watch", [
        _l("amazon", "B098KFXC93", 4995, original=6995, discount=28.59, rating=4.4),
        _l("flipkart", "ACCGZTITANRAGA", 4795, original=6995, discount=31.45, rating=4.4),
    ]),
    ("Fossil Men The Carlyle Chronograph Black Stainless Steel Watch", [
        _l("amazon", "B07PRKJ6FB", 12995, original=18495, discount=29.74, rating=4.6),
    ]),
    ("Daniel Wellington Classic Petite Melrose Women's Rose Gold Watch", [
        _l("nykaa", "BTYZHFGFBHFGZBD1", 9999, original=14500, discount=31.04, rating=4.5),
    ]),
    ("Garmin Forerunner 265 GPS Running Smartwatch with AMOLED Display", [
        _l("amazon", "B0BVPHMHCT", 41990, original=49990, discount=16.00, rating=4.7),
    ]),

    # ---- Kitchen + Home Extended ---------------------------------------
    ("Instant Pot Duo 7-in-1 Electric Pressure Cooker 5.7L", [
        _l("amazon", "B084VPK69M", 8499, original=12999, discount=34.65, rating=4.6),
    ]),
    ("Crompton Ameo Neo Geyser 25L Storage Water Heater", [
        _l("amazon", "B07Z6V35FH", 8499, original=14999, discount=43.34, rating=4.4),
    ]),
    ("Havells Magnetron 25L Convection Microwave Oven Black", [
        _l("amazon", "B07Y5QFDS5", 11990, original=18995, discount=36.88, rating=4.3),
        _l("flipkart", "HOMGZHAVELLSMW", 11490, original=18995, discount=39.51, rating=4.3),
    ]),
    ("Borosil Vision Glass Set of 6 Tumblers 350ml", [
        _l("amazon", "B07KLKYDH3", 545, original=940, discount=42.02, rating=4.5),
    ]),
    ("Milton Thermosteel Flip Lid Flask 1000ml Stainless Steel", [
        _l("amazon", "B00BYW6HMC", 695, original=1295, discount=46.33, rating=4.5),
    ]),
    ("Cello H2O Plastic Water Bottle Set of 6 1L Each Assorted", [
        _l("amazon", "B07JK4RSMJ", 549, original=900, discount=39.00, rating=4.4),
    ]),
    ("Prestige Omega Deluxe Granite Non-Stick Cookware Set 4-Piece", [
        _l("amazon", "B07X2N4Z3T", 2999, original=4995, discount=39.96, rating=4.3),
    ]),
    ("Hawkins Contura Hard Anodised Pressure Cooker 3 Litre", [
        _l("amazon", "B005O72UM6", 1995, original=2630, discount=24.14, rating=4.6),
    ]),
    ("Dyson V12 Detect Slim Cordless Vacuum Cleaner Yellow", [
        _l("amazon", "B0CQGBJSCP", 49900, original=54900, discount=9.11, rating=4.5),
    ]),

    # ---- More Beauty (Luxury & Indie) ----------------------------------
    ("Estée Lauder Advanced Night Repair Synchronized Multi-Recovery Complex 50 ml", [
        _l("nykaa", "BTYZHFGFBHFGZBD2", 7900, original=8400, discount=5.95, rating=4.7),
    ]),
    ("MAC Studio Fix Fluid Foundation SPF 15 NC42 30 ml", [
        _l("nykaa", "BTYZHFGFBHFGZBD3", 3300, original=3300, rating=4.6),
    ]),
    ("Charlotte Tilbury Pillow Talk Lipstick Original 3.5g", [
        _l("nykaa", "BTYZHFGFBHFGZBD4", 3450, original=3450, rating=4.7),
    ]),
    ("Huda Beauty Faux Filler Extra Shine Lip Gloss Honey Talks", [
        _l("nykaa", "BTYZHFGFBHFGZBD5", 1990, original=2200, discount=9.55, rating=4.5),
    ]),
    ("NARS Radiant Creamy Concealer Custard 6 ml", [
        _l("nykaa", "BTYZHFGFBHFGZBD6", 2950, original=2950, rating=4.6),
    ]),
    ("Innisfree Green Tea Hyaluronic Serum Hydrating 80 ml", [
        _l("nykaa", "BTYZHFGFBHFGZBD7", 1500, original=1850, discount=18.92, rating=4.5),
        _l("amazon", "B07RWLG6MZ", 1599, original=1850, discount=13.57, rating=4.4),
    ]),
    ("The Body Shop Vitamin E Moisture Cream 50 ml", [
        _l("nykaa", "BTYZHFGFBHFGZBD8", 1295, original=1395, discount=7.17, rating=4.5),
    ]),
    ("Forest Essentials Soundarya Radiance Cream Anti-Aging 50 g", [
        _l("nykaa", "BTYZHFGFBHFGZBD9", 4500, original=4500, rating=4.6),
    ]),
    ("Kama Ayurveda Kumkumadi Miraculous Beauty Fluid 25 ml", [
        _l("nykaa", "BTYZHFGFBHFGZBE1", 3895, original=3895, rating=4.5),
    ]),
    ("Sugar Cosmetics Ace of Face Foundation Stick Cocoa Loco", [
        _l("nykaa", "BTYZHFGFBHFGZBE2", 999, original=1299, discount=23.10, rating=4.4),
    ]),

    # ---- More Fragrance ------------------------------------------------
    ("Dior Sauvage Eau de Parfum for Men 100 ml", [
        _l("nykaa", "BTYZHFGFBHFGZBE3", 11900, original=11900, rating=4.8),
    ]),
    ("Chanel Coco Mademoiselle Eau de Parfum for Women 100 ml", [
        _l("nykaa", "BTYZHFGFBHFGZBE4", 14400, original=14400, rating=4.8),
    ]),
    ("Yves Saint Laurent Black Opium Eau de Parfum 90 ml", [
        _l("nykaa", "BTYZHFGFBHFGZBE5", 10500, original=11500, discount=8.70, rating=4.7),
    ]),
    ("Tom Ford Black Orchid Eau de Parfum Unisex 50 ml", [
        _l("nykaa", "BTYZHFGFBHFGZBE6", 14600, original=14600, rating=4.7),
    ]),
    ("Beardo Whisky Smoke Perfume for Men 100 ml", [
        _l("amazon", "B083T3MN98", 599, original=999, discount=40.04, rating=4.3),
    ]),

    # ---- Books (Extended) ----------------------------------------------
    ("The Alchemist by Paulo Coelho 25th Anniversary Edition", [
        _l("amazon", "0062315005", 350, original=499, discount=29.86, rating=4.6),
        _l("flipkart", "BKSGZTHEALCHEMIST", 320, original=499, discount=35.87, rating=4.6),
    ]),
    ("Think and Grow Rich by Napoleon Hill", [
        _l("amazon", "8189297937", 175, original=299, discount=41.47, rating=4.6),
    ]),
    ("Wings of Fire An Autobiography by A.P.J. Abdul Kalam", [
        _l("amazon", "8173711461", 199, original=295, discount=32.54, rating=4.7),
    ]),
    ("The 7 Habits of Highly Effective People by Stephen R. Covey", [
        _l("amazon", "1471195201", 379, original=499, discount=24.05, rating=4.7),
    ]),
    ("The Subtle Art of Not Giving a F*ck by Mark Manson", [
        _l("amazon", "0062457713", 299, original=499, discount=40.08, rating=4.5),
        _l("flipkart", "BKSGZSUBTLEART", 285, original=499, discount=42.89, rating=4.5),
    ]),
    ("A Brief History of Time by Stephen Hawking", [
        _l("amazon", "0553380168", 449, original=599, discount=25.04, rating=4.7),
    ]),
    ("The Power of Your Subconscious Mind by Joseph Murphy", [
        _l("amazon", "812221150X", 99, original=199, discount=50.25, rating=4.6),
    ]),

    # ---- Sports + Outdoors (Extended) ----------------------------------
    ("Decathlon Quechua MH100 30L Hiking Backpack Black", [
        _l("amazon", "B07RZBT9G2", 999, original=1499, discount=33.36, rating=4.4),
    ]),
    ("Yonex Astrox 88D Pro Badminton Racket Strung", [
        _l("amazon", "B0894KKWX1", 16990, original=21500, discount=20.98, rating=4.7),
    ]),
    ("Spalding NBA Indoor/Outdoor Basketball Size 7", [
        _l("amazon", "B07P9X1HKQ", 1899, original=2499, discount=24.01, rating=4.5),
    ]),
    ("Wilson US Open Junior Tennis Racket 25-inch", [
        _l("amazon", "B07VQNFY3M", 1799, original=2495, discount=27.90, rating=4.4),
    ]),
    ("Pro Spin Premium Table Tennis Bat with 2 Balls Carry Case", [
        _l("amazon", "B0BWPRZX5Y", 999, original=1799, discount=44.47, rating=4.3),
    ]),
    ("Boldfit Sports Skipping Rope with Counter Adjustable", [
        _l("amazon", "B07NBC4G86", 199, original=499, discount=60.12, rating=4.3),
    ]),
    ("Reebok Yoga Mat 4mm Non-Slip Pink Carry Strap Included", [
        _l("amazon", "B07L6XFRW1", 1499, original=2799, discount=46.45, rating=4.4),
    ]),

    # ---- Toys & Kids ---------------------------------------------------
    ("LEGO Classic Creative Bricks Box 484-Piece Set", [
        _l("amazon", "B00NHQF6MG", 1899, original=2499, discount=24.01, rating=4.7),
        _l("flipkart", "TOYGZLEGOBRICKS", 1799, original=2499, discount=28.01, rating=4.7),
    ]),
    ("Hot Wheels 20-Car Gift Pack Assorted Diecast Vehicles", [
        _l("amazon", "B07HWPFQ44", 1395, original=1799, discount=22.46, rating=4.6),
    ]),
    ("Funskool Monopoly Original Strategy Family Board Game", [
        _l("amazon", "B07R5JQR5T", 599, original=999, discount=40.04, rating=4.5),
    ]),

    # ---- Pet Supplies --------------------------------------------------
    ("Pedigree Adult Dry Dog Food Chicken & Vegetables 3 kg", [
        _l("amazon", "B07DRWNX1M", 695, original=895, discount=22.35, rating=4.5),
    ]),
    ("Whiskas Adult Cat Food Tuna Flavour 1.2 kg", [
        _l("amazon", "B07DRWWQXP", 549, original=695, discount=21.01, rating=4.5),
    ]),

    # ---- Health / Personal Care ----------------------------------------
    ("Oral-B Pro 1000 Electric Rechargeable Toothbrush Black", [
        _l("amazon", "B07HSWGD4P", 4499, original=6995, discount=35.68, rating=4.5),
    ]),
    ("Philips Sonicare DiamondClean Smart 9700 Sonic Toothbrush", [
        _l("amazon", "B083X6V2S2", 22995, original=27995, discount=17.86, rating=4.6),
    ]),
    ("Himalaya Wellness Pure Herbs Ashwagandha General Wellness 60 Tablets", [
        _l("amazon", "B0CFWYKKKN", 175, original=210, discount=16.67, rating=4.4),
    ]),
    ("Optimum Nutrition Gold Standard 100% Whey Protein Powder Vanilla 2 lb", [
        _l("amazon", "B0CBT8H8Y7", 4699, original=6299, discount=25.40, rating=4.6),
    ]),
    ("MuscleBlaze Biozyme Performance Whey 4.4 lb Chocolate", [
        _l("amazon", "B07Y6RNGN7", 6999, original=9499, discount=26.32, rating=4.5),
    ]),
]


_PLATFORM_SEARCH = {
    "amazon": "https://www.amazon.in/s?k={q}",
    "flipkart": "https://www.flipkart.com/search?q={q}",
    "nykaa": "https://www.nykaa.com/search/result/?q={q}",
}


def _platform_search_url(platform: str, title: str) -> str:
    """Land on the real platform's search results for the product title.

    We don't store deep-links because they go stale (the demo runs forever
    without re-scraping) and we'd be hotlinking content we don't control.
    A search URL is the most stable thing we can hand a clicker — it's a
    real Amazon / Flipkart / Nykaa page showing the product."""
    q = urllib.parse.quote_plus(title)
    template = _PLATFORM_SEARCH.get(platform)
    if template is None:
        return f"https://example.com/{q}"
    return template.format(q=q)


def _to_scraped(canonical_title: str, listing: dict) -> ScrapedListing:
    return ScrapedListing(
        platform=listing["platform"],
        platform_product_id=listing["pid"],
        title=canonical_title,
        price=Decimal(str(listing["price"])),
        original_price=Decimal(str(listing["original"])) if listing.get("original") else None,
        discount=Decimal(str(listing["discount"])) if listing.get("discount") else None,
        rating=Decimal(str(listing["rating"])) if listing.get("rating") else None,
        url=listing.get("url") or _platform_search_url(listing["platform"], canonical_title),
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
