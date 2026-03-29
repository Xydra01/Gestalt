"""
eBay live pricing via SerpApi.

Uses SerpApi's eBay engine (``engine=ebay``) and returns a normalized payload
that `price_comparison.py` can consume without changes.
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

_EBAY_SEARCH_BASE = "https://www.ebay.com/sch/i.html"

# Note returned by :func:`get_ebay_price` on success.
EBAY_PRICE_NOTE = "Live eBay price"


def ebay_search_url_for_query(query: str) -> str:
    """Direct link to eBay search results for ``query`` (used as the buy/search URL)."""
    nkw = quote_plus((query or "").strip())
    return f"{_EBAY_SEARCH_BASE}?_nkw={nkw}"


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


def _candidate_prices(item: dict[str, Any]) -> tuple[int | None, int | None]:
    """Return ``(buy_it_now_price, sold_or_fallback_price)`` for one result item."""
    is_buy_now = bool(item.get("buy_it_now"))

    primary = _parse_int_price(item.get("price"))
    sold = None
    for key in ("sold_price", "last_sold_price", "sold", "price_sold"):
        sold = _parse_int_price(item.get(key))
        if sold is not None:
            break

    bin_price = primary if is_buy_now else None
    sold_or_fallback = sold if sold is not None else primary
    return bin_price, sold_or_fallback


def scrape_ebay_price(query: str, api_key: str) -> int | None:
    """
    Fetch eBay live price using SerpApi (eBay engine).

    Request:
    - endpoint: ``https://serpapi.com/search.json``
    - params: ``api_key``, ``engine=ebay``, ``_nkw=query``, ``no_cache=true``,
      ``show_only=sold`` (market-value oriented demo mode)
    - timeout: 3 seconds

    Parsing:
    - prefers the first ``buy_it_now`` result's price
    - falls back to the first sold/regular price if no BIN result is present

    Returns:
    - integer price on success, else ``None``
    """
    q = (query or "").strip()
    k = (api_key or "").strip()
    if not q or not k:
        return None

    params = {
        "api_key": k,
        "engine": "ebay",
        "_nkw": q,
        "no_cache": "true",
        "show_only": "sold",
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
        organic_results = data.get("organic_results")
        if not isinstance(organic_results, list) or not organic_results:
            return None

        # Pass 1: explicit Buy It Now
        for item in organic_results:
            if not isinstance(item, dict):
                continue
            buy_now_price, _ = _candidate_prices(item)
            if isinstance(buy_now_price, int):
                return buy_now_price

        # Pass 2: first sold/regular fallback
        for item in organic_results:
            if not isinstance(item, dict):
                continue
            _, sold_or_fallback = _candidate_prices(item)
            if isinstance(sold_or_fallback, int):
                return sold_or_fallback

        return None
    except Exception:
        return None


def get_ebay_price(part_name: str, api_key: str | None = None) -> dict[str, Any] | None:
    """
    Look up a rough eBay price for a part name using SerpApi + eBay search.

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
