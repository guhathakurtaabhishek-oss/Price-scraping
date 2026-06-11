"""
Central configuration for the price scraper.
"""

MAX_PRODUCTS_PER_BRAND = 20          # cap for test runs; set to None for unlimited
REQUEST_TIMEOUT = 20                  # seconds
MIN_DELAY = 1.0                       # seconds between requests
MAX_DELAY = 2.0
MAX_RETRIES = 3

INPUT_FILE = "Price_Scrapping_data.xlsx"
OUTPUT_XLSX = "products_output.xlsx"
OUTPUT_CSV  = "products_output.csv"
FAILED_CSV  = "failed_urls.csv"

# URL path fragments that indicate a product page
PRODUCT_PATH_PATTERNS = [
    "/products/",
    "/product/",
    "/p/",
    "/shop/",
]

# Paths to skip (non-product)
SKIP_PATH_FRAGMENTS = [
    "/collections/",
    "/blogs/",
    "/pages/",
    "/account",
    "/cart",
    "/checkout",
    "/search",
    "/cdn",
    "/assets",
    "#",
    "javascript:",
    "mailto:",
    "tel:",
    ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp",
    ".pdf", ".zip",
]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

# Base headers — User-Agent is rotated per request in make_headers()
BASE_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-IN,en-GB;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
    "DNT": "1",
}

# Keep for backwards compat — actual requests use make_headers()
HEADERS = {**BASE_HEADERS, "User-Agent": USER_AGENTS[0]}

OUTPUT_COLUMNS = [
    "Brand Name",
    "Source Brand URL",
    "Product URL",
    "Product Name",
    "MRP",
    "Selling Price / Final Price",
    "Discount %",
    "Coupon Code",
    "Prepaid Offer",
    "Shipping Fee",
    "Availability / Stock Status",
]
