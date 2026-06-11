"""
URL discovery: sitemap → Shopify products.json → collection page crawl.
Returns a deduplicated list of product URLs for a given brand website.
"""

import logging
import re
import time
import random
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

import config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared HTTP helper
# ---------------------------------------------------------------------------

def _get(url: str, session: requests.Session, stream=False) -> requests.Response | None:
    """GET with retries and polite delay. Returns None on unrecoverable failure."""
    for attempt in range(1, config.MAX_RETRIES + 1):
        try:
            time.sleep(random.uniform(config.MIN_DELAY, config.MAX_DELAY))
            resp = session.get(
                url,
                headers=config.HEADERS,
                timeout=config.REQUEST_TIMEOUT,
                stream=stream,
                allow_redirects=True,
            )
            if resp.status_code == 200:
                return resp
            if resp.status_code in (429, 503):
                wait = 2 ** attempt
                logger.warning("Rate-limited on %s. Waiting %ds…", url, wait)
                time.sleep(wait)
            elif resp.status_code in (403, 404, 410):
                logger.debug("HTTP %d for %s — skipping.", resp.status_code, url)
                return None
            else:
                logger.debug("HTTP %d for %s (attempt %d)", resp.status_code, url, attempt)
        except requests.RequestException as exc:
            logger.warning("Request error for %s (attempt %d): %s", url, attempt, exc)
    return None


# ---------------------------------------------------------------------------
# URL filters
# ---------------------------------------------------------------------------

def _is_product_url(url: str, base_domain: str) -> bool:
    parsed = urlparse(url)
    # Must belong to the same domain
    if base_domain not in parsed.netloc:
        return False
    path = parsed.path.lower()
    if not any(pat in path for pat in config.PRODUCT_PATH_PATTERNS):
        return False
    if any(frag in path for frag in config.SKIP_PATH_FRAGMENTS):
        return False
    return True


def _normalise(url: str) -> str:
    """Strip query-strings and fragments for dedup."""
    p = urlparse(url)
    return p._replace(query="", fragment="").geturl().rstrip("/")


# ---------------------------------------------------------------------------
# Strategy 1: Sitemap
# ---------------------------------------------------------------------------

def _parse_sitemap(url: str, session: requests.Session, base_domain: str,
                   collected: set, depth=0):
    if depth > 4:
        return
    resp = _get(url, session)
    if not resp:
        return
    try:
        soup = BeautifulSoup(resp.content, "lxml-xml")
    except Exception:
        soup = BeautifulSoup(resp.content, "html.parser")

    # Sitemap index → recurse
    for loc in soup.find_all("sitemap"):
        child_url = loc.find("loc")
        if child_url:
            _parse_sitemap(child_url.text.strip(), session, base_domain, collected, depth + 1)

    # Regular sitemap URLs
    for loc in soup.find_all("url"):
        loc_tag = loc.find("loc")
        if not loc_tag:
            continue
        u = loc_tag.text.strip()
        norm = _normalise(u)
        if _is_product_url(norm, base_domain):
            collected.add(norm)


def _discover_via_sitemap(base_url: str, session: requests.Session,
                          base_domain: str) -> set:
    found: set = set()
    candidates = [
        urljoin(base_url, "/sitemap.xml"),
        urljoin(base_url, "/sitemap_index.xml"),
        urljoin(base_url, "/sitemaps/sitemap.xml"),
        urljoin(base_url, "/sitemap/sitemap.xml"),
    ]
    for sitemap_url in candidates:
        _parse_sitemap(sitemap_url, session, base_domain, found)
        if found:
            break
    logger.info("Sitemap found %d product URLs on %s", len(found), base_url)
    return found


# ---------------------------------------------------------------------------
# Strategy 2: Shopify products.json
# ---------------------------------------------------------------------------

def _discover_via_shopify(base_url: str, session: requests.Session,
                          base_domain: str) -> set:
    found: set = set()
    page = 1
    while True:
        url = f"{base_url.rstrip('/')}/products.json?limit=250&page={page}"
        resp = _get(url, session)
        if not resp:
            break
        try:
            data = resp.json()
        except Exception:
            break
        products = data.get("products", [])
        if not products:
            break
        for p in products:
            handle = p.get("handle", "")
            if handle:
                product_url = _normalise(f"{base_url.rstrip('/')}/products/{handle}")
                found.add(product_url)
        if len(products) < 250:
            break
        page += 1
    if found:
        logger.info("Shopify products.json found %d URLs on %s", len(found), base_url)
    return found


# ---------------------------------------------------------------------------
# Strategy 3: Collection / category page crawl
# ---------------------------------------------------------------------------

_COLLECTION_PATHS = [
    "/collections/all",
    "/collections",
    "/shop",
    "/shop/all",
    "/products",
    "/category/all",
    "/all-products",
]


def _extract_links(html: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for tag in soup.find_all("a", href=True):
        href = tag["href"].strip()
        if not href:
            continue
        full = urljoin(base_url, href)
        links.append(full)
    return links


def _discover_via_crawl(base_url: str, session: requests.Session,
                        base_domain: str) -> set:
    found: set = set()
    visited: set = set()

    def crawl(url: str, depth: int):
        norm = _normalise(url)
        if norm in visited or depth > 2:
            return
        visited.add(norm)
        resp = _get(url, session)
        if not resp:
            return
        for link in _extract_links(resp.text, base_url):
            lnorm = _normalise(link)
            if _is_product_url(lnorm, base_domain):
                found.add(lnorm)
            elif (
                base_domain in urlparse(link).netloc
                and depth < 2
                and not any(f in link.lower() for f in config.SKIP_PATH_FRAGMENTS)
                and lnorm not in visited
            ):
                # Only recurse into collection/category-like pages
                path = urlparse(link).path.lower()
                if any(kw in path for kw in ["/collection", "/category", "/shop", "/products"]):
                    crawl(link, depth + 1)

    # Try known collection paths first
    for path in _COLLECTION_PATHS:
        crawl(urljoin(base_url, path), depth=0)
        if len(found) >= (config.MAX_PRODUCTS_PER_BRAND or 500):
            break

    # Also crawl homepage
    if not found:
        crawl(base_url, depth=0)

    logger.info("Crawl found %d product URLs on %s", len(found), base_url)
    return found


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def discover_product_urls(brand_name: str, base_url: str,
                          session: requests.Session) -> list[str]:
    """
    Discover product URLs for a brand using all available strategies.
    Returns a deduplicated, capped list.
    """
    base_domain = urlparse(base_url).netloc.replace("www.", "")
    logger.info("=== Discovering URLs for %s (%s) ===", brand_name, base_url)

    all_urls: set = set()

    # 1. Sitemap
    all_urls |= _discover_via_sitemap(base_url, session, base_domain)

    # 2. Shopify products.json (try regardless; returns empty if not Shopify)
    if len(all_urls) < 10:
        all_urls |= _discover_via_shopify(base_url, session, base_domain)

    # 3. Crawl if still thin
    if len(all_urls) < 5:
        all_urls |= _discover_via_crawl(base_url, session, base_domain)

    cap = config.MAX_PRODUCTS_PER_BRAND
    result = list(all_urls)
    if cap:
        result = result[:cap]

    logger.info("Total unique product URLs for %s: %d (capped at %s)",
                brand_name, len(result), cap)
    return result
