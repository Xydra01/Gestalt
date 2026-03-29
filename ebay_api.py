"""
eBay search result pricing via `ScrapingBee <https://www.scrapingbee.com/>`_.

ScrapingBee handles all proxies and CAPTCHAs. We just call their API.

Hackathon / demo: HTML layout can change; parsing targets current eBay classes
(``s-item``, ``s-item__price``, etc.).
"""

from __future__ import annotations

import os
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus, urlencode
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

# Environment variable for :func:`get_ebay_price`.
SCRAPINGBEE_API_KEY_ENV = "SCRAPINGBEE_API_KEY"

_SCRAPINGBEE_API_URL = "https://app.scrapingbee.com/api/v1/"
_EBAY_SEARCH_BASE = "https://www.ebay.com/sch/i.html"
_REQUEST_TIMEOUT_SEC = 3

# Note returned by :func:`get_ebay_price` on success.
EBAY_PRICE_NOTE = "Live eBay price"


def _parse_price_to_int(price_text: str) -> int | None:
    """Turn a price string like ``'$1,234.56'`` or ``'$10.00 to $20'`` into a whole-dollar int."""
    if not price_text or not price_text.strip():
        return None
    # Prefer the first money token (handles " $12.99 " and ranges by taking start).
    chunk = price_text.replace(",", "").strip()
    if " to " in chunk.lower():
        chunk = re.split(r"\s+to\s+", chunk, maxsplit=1, flags=re.I)[0].strip()
    match = re.search(r"(\d+(?:\.\d+)?)", chunk)
    if not match:
        return None
    try:
        return int(round(float(match.group(1))))
    except (TypeError, ValueError):
        return None


def _is_junk_placeholder(item: Any) -> bool:
    """Skip the decorative first row (e.g. 'Shop on eBay')."""
    title_el = item.select_one(".s-item__title")
    if title_el:
        t = title_el.get_text(strip=True).lower()
        if "shop on ebay" in t or not t:
            return True
    return False


def _listing_is_buy_it_now_or_fixed(item: Any) -> bool:
    """
    Heuristic: prefer explicit Buy It Now; otherwise treat as fixed-price if
    the block does not look like a pure auction line.
    """
    text = item.get_text(" ", strip=True).lower()
    if "buy it now" in text:
        return True
    if "see price" in text:
        return False
    # Auction-style hints
    if re.search(r"\b\d+\s+bids?\b", text):
        return False
    if "place bid" in text or "time left" in text:
        return False
    return True


def _first_bin_or_fixed_price_int(soup: BeautifulSoup) -> int | None:
    """
    Walk search result rows; return the first suitable ``s-item__price`` as int.

    Prioritizes listings that mention Buy It Now, then other non-auction fixed prices.
    """
    items = soup.select("li.s-item")
    if not items:
        return None

    # Pass 1: explicit Buy It Now
    for item in items:
        if _is_junk_placeholder(item):
            continue
        price_el = item.select_one(".s-item__price")
        if not price_el:
            continue
        blob = item.get_text(" ", strip=True).lower()
        if "buy it now" not in blob:
            continue
        val = _parse_price_to_int(price_el.get_text())
        if val is not None:
            return val

    # Pass 2: fixed-price style (no bidding cues)
    for item in items:
        if _is_junk_placeholder(item):
            continue
        if not _listing_is_buy_it_now_or_fixed(item):
            continue
        price_el = item.select_one(".s-item__price")
        if not price_el:
            continue
        val = _parse_price_to_int(price_el.get_text())
        if val is not None:
            return val

    return None


def scrape_ebay_price(query: str, api_key: str) -> int | None:
    """
    Fetch eBay search HTML via ScrapingBee and return the first suitable BIN/fixed price.

    Calls ``GET https://app.scrapingbee.com/api/v1/`` with ``api_key``, ``url`` (eBay
    search for ``query``), ``render_js=false``, and ``wait=0``. Uses a 3-second timeout.

    Parses the HTML with BeautifulSoup: walks ``li.s-item`` rows, skips placeholders,
    prefers listings that include Buy It Now, then other fixed-price-style rows, and
    reads ``.s-item__price``.

    Returns:
        First matching price as an integer (whole dollars), or ``None`` on failure.

    Args:
        query: Search string (e.g. PC part name).
        api_key: ScrapingBee API key.

    Note:
        Any network error, HTTP error, timeout, parse failure, or missing price
        yields ``None``.
    """
    if not (query and str(query).strip() and api_key and str(api_key).strip()):
        return None

    nkw = quote_plus(query.strip())
    ebay_url = f"{_EBAY_SEARCH_BASE}?_nkw={nkw}"

    params = {
        "api_key": api_key.strip(),
        "url": ebay_url,
        "render_js": "false",
        "wait": "0",
    }
    full_url = f"{_SCRAPINGBEE_API_URL}?{urlencode(params)}"

    try:
        req = Request(full_url, headers={"Accept": "text/html,application/xhtml+xml"})
        with urlopen(req, timeout=_REQUEST_TIMEOUT_SEC) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except (HTTPError, URLError, TimeoutError, OSError):
        return None

    try:
        soup = BeautifulSoup(body, "html.parser")
    except Exception:
        return None

    return _first_bin_or_fixed_price_int(soup)


def get_ebay_price(part_name: str, scrapingbee_key: str | None = None) -> dict[str, Any] | None:
    """
    Look up a rough eBay price for a part name using ScrapingBee + eBay search.

    Uses ``scrapingbee_key`` when non-empty; otherwise ``SCRAPINGBEE_API_KEY`` from
    the environment. If no key is available or scraping fails, returns ``None``.

    Returns:
        ``{"source": "ebay", "price": int, "note": "Live eBay price"}`` on success,
        else ``None``.
    """
    api_key = (scrapingbee_key or "").strip() or os.environ.get(SCRAPINGBEE_API_KEY_ENV, "").strip()
    if not api_key:
        return None

    price = scrape_ebay_price(part_name, api_key)
    if price is None:
        return None

    return {
        "source": "ebay",
        "price": price,
        "note": EBAY_PRICE_NOTE,
    }
