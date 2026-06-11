#!/usr/bin/env python3
"""
Price Scraper — main entry point.

Usage:
    python scraper.py                          # uses default input file from config.py
    python scraper.py --input myfile.xlsx      # custom input file
    python scraper.py --max 50                 # override products-per-brand cap
    python scraper.py --brands "Mamaearth,XYXX"  # scrape specific brands only
"""

import argparse
import logging
import sys
import time
import random
from pathlib import Path

import requests
import openpyxl

import config
from discovery import discover_product_urls, _make_headers
from extractor import extract_product
from storage import append_record, save_results

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("scraper.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Input reading
# ---------------------------------------------------------------------------

def read_input(filepath: str) -> list[dict]:
    path = Path(filepath)
    if not path.exists():
        logger.error("Input file not found: %s", filepath)
        sys.exit(1)

    brands = []
    wb = openpyxl.load_workbook(filepath)
    ws = wb.active
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i == 0:
            continue  # skip header
        if not row[0]:
            continue
        brand_name = str(row[0]).strip()
        website    = str(row[1]).strip() if len(row) > 1 and row[1] else ""
        if website:
            if not website.startswith("http"):
                website = "https://" + website
            brands.append({"brand": brand_name, "url": website})
    logger.info("Loaded %d brands from %s", len(brands), filepath)
    return brands


# ---------------------------------------------------------------------------
# Per-product fetch
# ---------------------------------------------------------------------------

def fetch_product(brand_name: str, source_brand_url: str, url: str,
                  session: requests.Session) -> tuple[dict | None, str | None]:
    """
    Fetch one product page and extract data.
    Returns (record_dict, None) on success or (None, error_reason) on failure.
    """
    try:
        time.sleep(random.uniform(config.MIN_DELAY, config.MAX_DELAY))
        resp = session.get(
            url,
            headers=_make_headers(referer=source_brand_url),
            timeout=config.REQUEST_TIMEOUT,
            allow_redirects=True,
        )
    except requests.RequestException as exc:
        return None, str(exc)

    if resp.status_code == 403:
        return None, "HTTP 403 — bot-blocked by site WAF"
    if resp.status_code != 200:
        return None, f"HTTP {resp.status_code}"

    # Skip CAPTCHA / bot-detection pages (don't try to bypass)
    lower = resp.text.lower()
    if any(kw in lower for kw in ["captcha", "just a moment", "enable javascript and cookies",
                                   "access denied", "403 forbidden", "blocked"]):
        return None, "Blocked / CAPTCHA"

    try:
        record = extract_product(brand_name, source_brand_url, url, resp.text)
    except Exception as exc:
        return None, f"Extraction error: {exc}"

    return record, None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Brand price scraper")
    parser.add_argument("--input",  default=config.INPUT_FILE,
                        help="Path to input .xlsx file")
    parser.add_argument("--max",    type=int, default=config.MAX_PRODUCTS_PER_BRAND,
                        help="Max products per brand (0 = unlimited)")
    parser.add_argument("--brands", default="",
                        help="Comma-separated brand names to limit run to")
    args = parser.parse_args()

    if args.max is not None:
        config.MAX_PRODUCTS_PER_BRAND = args.max or None

    brand_filter = {b.strip().lower() for b in args.brands.split(",") if b.strip()}

    brands = read_input(args.input)
    if brand_filter:
        brands = [b for b in brands if b["brand"].lower() in brand_filter]
        logger.info("Filtered to brands: %s", [b["brand"] for b in brands])

    session = requests.Session()
    session.headers.update(config.HEADERS)

    all_records: list[dict] = []
    all_failed:  list[dict] = []

    for brand_info in brands:
        brand_name = brand_info["brand"]
        base_url   = brand_info["url"]

        logger.info("")
        logger.info("━━━ %s (%s) ━━━", brand_name, base_url)

        # --- Discover product URLs ---
        try:
            product_urls = discover_product_urls(brand_name, base_url, session)
        except Exception as exc:
            logger.error("URL discovery failed for %s: %s", brand_name, exc)
            all_failed.append({"Brand Name": brand_name, "URL": base_url,
                                "Reason": f"Discovery failed: {exc}"})
            continue

        if not product_urls:
            logger.warning("No product URLs found for %s", brand_name)
            all_failed.append({"Brand Name": brand_name, "URL": base_url,
                                "Reason": "No product URLs discovered"})
            continue

        logger.info("Scraping %d product pages for %s…", len(product_urls), brand_name)

        brand_ok    = 0
        brand_fail  = 0

        for url in product_urls:
            record, err = fetch_product(brand_name, base_url, url, session)

            if err:
                logger.warning("  FAIL  %s  [%s]", url, err)
                all_failed.append({"Brand Name": brand_name, "URL": url, "Reason": err})
                brand_fail += 1
            else:
                all_records.append(record)
                append_record(record)  # incremental write
                brand_ok += 1
                sp  = record["Selling Price / Final Price"]
                mrp = record["MRP"]
                logger.info("  OK    %s  |  %s  |  SP=%s  MRP=%s",
                            brand_name,
                            (record["Product Name"] or "")[:40],
                            f"{sp:.0f}" if sp else "-",
                            f"{mrp:.0f}" if mrp else "-")

        logger.info("Brand summary — %s: %d OK / %d failed",
                    brand_name, brand_ok, brand_fail)

    # --- Final save ---
    save_results(all_records, all_failed)

    logger.info("")
    logger.info("═══ DONE ═══")
    logger.info("Total products scraped : %d", len(all_records))
    logger.info("Total failures         : %d", len(all_failed))
    logger.info("Output files: %s  |  %s  |  %s",
                config.OUTPUT_XLSX, config.OUTPUT_CSV, config.FAILED_CSV)


if __name__ == "__main__":
    main()
