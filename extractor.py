"""
Product data extraction from a product page.
Priority order:
  1. JSON-LD (application/ld+json with @type Product)
  2. Shopify meta/window.ShopifyAnalytics
  3. HTML / meta-tag fallback
"""

import json
import logging
import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Price cleaning
# ---------------------------------------------------------------------------

def _clean_price(raw) -> float | None:
    if raw is None:
        return None
    s = str(raw).replace(",", "").strip()
    # Remove currency symbols / text (₹, Rs., INR, $, etc.)
    s = re.sub(r"[₹$£€]|Rs\.?|INR|MRP|mrp", "", s, flags=re.IGNORECASE).strip()
    # Take first numeric-looking token
    m = re.search(r"\d+(?:\.\d+)?", s)
    if m:
        return float(m.group())
    return None


def _discount(mrp: float | None, sp: float | None) -> float | None:
    if mrp and sp and mrp > 0 and sp < mrp:
        return round((mrp - sp) / mrp * 100, 2)
    return None


# ---------------------------------------------------------------------------
# Strategy 1: JSON-LD
# ---------------------------------------------------------------------------

def _from_json_ld(soup: BeautifulSoup) -> dict:
    result = {}
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except Exception:
            continue

        # May be a single object or a list
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            t = item.get("@type", "")
            types = t if isinstance(t, list) else [t]
            if "Product" not in types:
                continue

            result["name"] = item.get("name", "")

            offers = item.get("offers") or item.get("Offers")
            if isinstance(offers, list):
                offers = offers[0] if offers else {}
            if isinstance(offers, dict):
                result["selling_price"] = _clean_price(
                    offers.get("price") or offers.get("lowPrice")
                )
                result["mrp"] = _clean_price(
                    offers.get("highPrice") or offers.get("priceBeforeDiscount")
                )
                avail = str(offers.get("availability", "")).lower()
                if "instock" in avail or "in_stock" in avail:
                    result["stock"] = "In Stock"
                elif "outofstock" in avail or "out_of_stock" in avail:
                    result["stock"] = "Out of Stock"
                else:
                    result["stock"] = avail or ""

            if result.get("name"):
                return result
    return result


# ---------------------------------------------------------------------------
# Strategy 2: Shopify window.__st / ShopifyAnalytics meta
# ---------------------------------------------------------------------------

def _from_shopify_meta(soup: BeautifulSoup, html: str) -> dict:
    result = {}

    # Try meta[property="product:price:amount"] (Open Graph Commerce)
    price_tag = soup.find("meta", {"property": "product:price:amount"})
    if price_tag:
        result["selling_price"] = _clean_price(price_tag.get("content"))

    # Try window.ShopifyAnalytics.meta.product inline JSON
    m = re.search(
        r"ShopifyAnalytics\.meta\s*=\s*(\{.*?\});",
        html, re.DOTALL
    )
    if m:
        try:
            meta = json.loads(m.group(1))
            product = meta.get("product", {})
            result.setdefault("name", product.get("title", ""))
        except Exception:
            pass

    # window.meta.product
    m2 = re.search(r'"price"\s*:\s*(\d+(?:\.\d+)?)', html)
    if m2 and not result.get("selling_price"):
        val = float(m2.group(1))
        # Shopify prices are in paise/cents when integer > 1000? Usually not for INR
        # heuristic: if > 10000, might be paise
        if val > 10000:
            val = val / 100
        result["selling_price"] = val

    return result


# ---------------------------------------------------------------------------
# Strategy 3: HTML / meta fallback
# ---------------------------------------------------------------------------

# CSS selectors tried in order (first match wins)
_NAME_SELECTORS = [
    "h1.product-title",
    "h1.product__title",
    "h1.product_title",
    "h1[itemprop='name']",
    "h1.pdp-title",
    "h1.pdp__product-name",
    ".product-name h1",
    ".product__name",
    "h1",
]

_SP_SELECTORS = [
    "[itemprop='price']",
    ".product__price .price",
    ".product-price .price",
    ".price-item--sale",
    ".price-item--regular",
    ".pdp-price",
    ".selling-price",
    ".offer-price",
    ".final-price",
    ".product__current-price",
    ".current-price",
    "span.price",
]

_MRP_SELECTORS = [
    ".compare-at-price",
    ".price--compare",
    ".was-price",
    ".original-price",
    ".price-item--regular",
    "[data-compare-price]",
    ".product__compare-price",
    ".mrp",
    "del",
    "s.price",
]

_STOCK_SELECTORS = [
    "[itemprop='availability']",
    ".product-availability",
    ".stock-status",
    ".availability",
    ".in-stock",
    ".out-of-stock",
    ".sold-out",
]


def _first_text(soup: BeautifulSoup, selectors: list[str]) -> str:
    for sel in selectors:
        try:
            el = soup.select_one(sel)
        except Exception:
            continue
        if el:
            return el.get_text(strip=True)
    return ""


def _from_html(soup: BeautifulSoup) -> dict:
    result = {}

    # Name
    name = _first_text(soup, _NAME_SELECTORS)
    if not name:
        og = soup.find("meta", {"property": "og:title"})
        name = og["content"].strip() if og and og.get("content") else ""
    result["name"] = name

    # Selling price
    sp_text = _first_text(soup, _SP_SELECTORS)
    result["selling_price"] = _clean_price(sp_text)

    # MRP / compare-at price
    mrp_text = _first_text(soup, _MRP_SELECTORS)
    result["mrp"] = _clean_price(mrp_text)

    # Stock
    stock_text = _first_text(soup, _STOCK_SELECTORS).lower()
    if "in stock" in stock_text or "in-stock" in stock_text or "available" in stock_text:
        result["stock"] = "In Stock"
    elif "out of stock" in stock_text or "sold out" in stock_text or "unavailable" in stock_text:
        result["stock"] = "Out of Stock"
    else:
        # Check add-to-cart button state
        btn = soup.select_one("button[name='add'], .add-to-cart, .btn-add-to-cart, #AddToCart")
        if btn:
            if btn.get("disabled") or "sold-out" in btn.get("class", []):
                result["stock"] = "Out of Stock"
            else:
                result["stock"] = "In Stock"
        else:
            result["stock"] = ""

    return result


# ---------------------------------------------------------------------------
# Coupon / offer / shipping extraction (best-effort)
# ---------------------------------------------------------------------------

_COUPON_PATTERNS = [
    r"(?:use\s+code|coupon\s*code|promo\s*code|offer\s*code)[:\s]+([A-Z0-9]{3,20})",
    r"code\s*[:\-]\s*([A-Z0-9]{3,20})",
]

_PREPAID_PATTERNS = [
    r"(?:extra|additional)\s+[\d]+%?\s+off\s+on\s+prepaid",
    r"prepaid\s+(?:discount|offer)[:\s]+([^\.\n<]{5,60})",
    r"([\d]+%?\s+(?:extra\s+)?off\s+on\s+prepaid[^\.\n<]{0,40})",
]

_SHIPPING_PATTERNS = [
    r"free\s+(?:shipping|delivery)(?:\s+on\s+orders?\s+(?:above|over|of)\s+(?:₹|Rs\.?|INR)?\s*([\d,]+))?",
    r"(?:shipping|delivery)\s+(?:fee|charge)[:\s]+(?:₹|Rs\.?|INR)?\s*([\d,]+)",
    r"(?:₹|Rs\.?|INR)?\s*([\d,]+)\s+(?:shipping|delivery)",
]


def _extract_offers(html: str) -> dict:
    result = {"coupon": "", "prepaid_offer": "", "shipping_fee": ""}
    text = html  # search raw HTML for these patterns

    for pat in _COUPON_PATTERNS:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            result["coupon"] = m.group(1).strip().upper()
            break

    for pat in _PREPAID_PATTERNS:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            result["prepaid_offer"] = m.group(0).strip()[:120]
            break

    for pat in _SHIPPING_PATTERNS:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            result["shipping_fee"] = m.group(0).strip()[:80]
            break

    return result


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def extract_product(brand_name: str, product_url: str, html: str) -> dict:
    """
    Extract product details from page HTML.
    Returns a dict with all OUTPUT_COLUMNS keys.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Try each strategy; merge with later strategies filling gaps
    data: dict = {}

    jld = _from_json_ld(soup)
    shop = _from_shopify_meta(soup, html)
    html_data = _from_html(soup)
    offers = _extract_offers(html)

    # Merge: JSON-LD wins, then Shopify meta, then HTML
    name = jld.get("name") or shop.get("name") or html_data.get("name") or ""
    selling_price = jld.get("selling_price") or shop.get("selling_price") or html_data.get("selling_price")
    mrp = jld.get("mrp") or html_data.get("mrp")
    stock = jld.get("stock") or html_data.get("stock") or ""

    # If MRP not found separately but SP found, set MRP = SP (no discount)
    if selling_price and not mrp:
        mrp = selling_price

    discount = _discount(mrp, selling_price)

    # Final price heuristic (selling price unless a prepaid discount bumps it down)
    final_price = selling_price

    return {
        "Brand Name": brand_name,
        "Product Name": name.strip(),
        "Product URL": product_url,
        "MRP": mrp,
        "Selling Price": selling_price,
        "Discount %": discount,
        "Coupon Code": offers["coupon"],
        "Prepaid Offer": offers["prepaid_offer"],
        "Shipping Fee": offers["shipping_fee"],
        "Final Price": final_price,
        "Stock Status": stock,
        "Scraped Timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
    }
