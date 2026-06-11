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

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

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
