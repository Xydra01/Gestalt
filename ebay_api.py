"""
Live pricing via SerpApi Google Shopping.

Legacy function names are kept for compatibility with callers:
``scrape_ebay_price`` and ``get_ebay_price``.

Reality note:
The output fields still use the label ``source: \"ebay\"`` for UI/backward compatibility, but
this module does not scrape eBay HTML anymore; it queries SerpApi's Google Shopping engine.
"""

from __future__ import annotations

import os
import re
from typing import Any
from urllib.parse import quote_plus

import requests

# Environment variable for :func:`get_ebay_price`.
SERPAPI_API_KEY_ENV = "SERPAPI_API_KEY"
_SERPAPI_URL = "https://serpapi.com/search.json"
_REQUEST_TIMEOUT_SEC = 3

_SHOPPING_SEARCH_BASE = "https://www.google.com/search?tbm=shop"

# Note returned by :func:`get_ebay_price` on success.
EBAY_PRICE_NOTE = "Live eBay price"


def ebay_search_url_for_query(query: str) -> str:
    """Direct link to Google Shopping results for ``query`` (legacy helper name)."""
    q = quote_plus((query or "").strip())
    return f"{_SHOPPING_SEARCH_BASE}&q={q}"


def _parse_int_price(raw: Any) -> int | None:
    """Extract an integer dollar price from mixed SerpApi price values."""
    if isinstance(raw, (int, float)):
        return int(round(float(raw)))
    if isinstance(raw, dict):
        for key in ("value", "extracted_value", "amount", "raw"):
            v = _parse_int_price(raw.get(key))
            if v is not None:
                return v
        return None
    if raw is None:
        return None
    text = str(raw)
    m = re.search(r"[\d,]+(?:\.\d+)?", text)
    if not m:
        return None
    try:
        return int(float(m.group(0).replace(",", "")))
    except (TypeError, ValueError):
        return None


def _result_price(item: dict[str, Any]) -> int | None:
    """Parse first usable numeric price from a Google Shopping result item."""
    for key in ("extracted_price", "price", "price_raw"):
        price = _parse_int_price(item.get(key))
        if isinstance(price, int):
            return price
    return None


def scrape_ebay_price(query: str, api_key: str) -> int | None:
    """
    Fetch live market price using SerpApi Google Shopping.

    Request:
    - endpoint: ``https://serpapi.com/search.json``
    - params: ``api_key``, ``engine=google_shopping``, ``q=query``, ``no_cache=true``
    - timeout: 3 seconds

    Parsing:
    - first parseable price in ``shopping_results``
    - fallback: ``inline_shopping_results`` then ``organic_results``

    Returns:
    - integer price on success, else ``None``
    """
    q = (query or "").strip()
    k = (api_key or "").strip()
    if not q or not k:
        return None

    params = {
        "api_key": k,
        "engine": "google_shopping",
        "q": q,
        "no_cache": "true",
    }

    try:
        response = requests.get(
            _SERPAPI_URL, params=params, timeout=_REQUEST_TIMEOUT_SEC
        )
        if response.status_code != 200:
            return None

        data = response.json()
        if not isinstance(data, dict):
            return None
        for key in ("shopping_results", "inline_shopping_results", "organic_results"):
            results = data.get(key)
            if not isinstance(results, list):
                continue
            for item in results:
                if not isinstance(item, dict):
                    continue
                price = _result_price(item)
                if isinstance(price, int):
                    return price

        return None
    except Exception:
        return None


def get_ebay_price(part_name: str, api_key: str | None = None) -> dict[str, Any] | None:
    """
    Look up live market price for a part name via SerpApi Google Shopping.

    Uses ``api_key`` when non-empty; otherwise reads ``SERPAPI_API_KEY``.
    Returns ``None`` on any failure.
    """
    key = (api_key or "").strip() or os.environ.get(SERPAPI_API_KEY_ENV, "").strip()
    if not key:
        return None

    price = scrape_ebay_price(part_name, key)
    if price is None:
        return None

    return {
        "source": "ebay",
        "price": price,
        "note": EBAY_PRICE_NOTE,
        "url": ebay_search_url_for_query(part_name),
    }
