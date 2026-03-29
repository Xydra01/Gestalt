"""
Amazon product search via Rainforest API (hackathon / demo).

Uses the public request endpoint with ``type=search``. Requires a valid API key
from https://www.rainforestapi.com/
"""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

# Environment variable used by :func:`get_amazon_price` when no key is passed in code.
RAINFOREST_API_KEY_ENV = "RAINFOREST_API_KEY"

_RAINFOREST_REQUEST_URL = "https://api.rainforestapi.com/request"
_REQUEST_TIMEOUT_SEC = 3


def _extract_first_result_price_title(product: dict[str, Any]) -> tuple[int, str] | None:
    """Parse Rainforest search result item into ``(price_int, title)`` or ``None``."""
    title = product.get("title")
    if not title or not isinstance(title, str):
        return None

    value: float | int | None = None
    price_obj = product.get("price")
    if isinstance(price_obj, dict):
        raw = price_obj.get("value")
        if isinstance(raw, (int, float)):
            value = raw

    if value is None:
        prices = product.get("prices")
        if isinstance(prices, list) and prices:
            first = prices[0]
            if isinstance(first, dict):
                raw = first.get("value")
                if isinstance(raw, (int, float)):
                    value = raw

    if value is None:
        return None

    price_int = int(round(float(value)))
    return (price_int, title)


def search_amazon(query: str, api_key: str) -> tuple[int, str] | None:
    """
    Search Amazon via Rainforest API and return the first organic result's price and title.

    Calls ``GET https://api.rainforestapi.com/request`` with ``api_key``, ``type=search``,
    and ``search_term`` set to ``query``. Uses a 3-second socket timeout.

    Returns:
        ``(price, title)`` where ``price`` is a whole-dollar integer (rounded from the API
        float) and ``title`` is the listing title, or ``None`` if the request fails,
        times out, returns invalid JSON, has no results, or the first hit has no usable
        price/title.

    Args:
        query: Search string (e.g. PC part name).
        api_key: Rainforest API key.

    Note:
        Network errors, HTTP errors, empty keys, and malformed payloads all yield ``None``.
    """
    if not (query and str(query).strip() and api_key and str(api_key).strip()):
        return None

    params = urlencode(
        {
            "api_key": api_key.strip(),
            "type": "search",
            "search_term": query.strip(),
        }
    )
    url = f"{_RAINFOREST_REQUEST_URL}?{params}"

    try:
        req = Request(url, headers={"Accept": "application/json"})
        with urlopen(req, timeout=_REQUEST_TIMEOUT_SEC) as resp:
            body = resp.read().decode("utf-8")
    except (HTTPError, URLError, TimeoutError, OSError):
        return None

    try:
        data: Any = json.loads(body)
    except json.JSONDecodeError:
        return None

    if not isinstance(data, dict):
        return None

    results = data.get("search_results")
    if not isinstance(results, list) or not results:
        return None

    first = results[0]
    if not isinstance(first, dict):
        return None

    return _extract_first_result_price_title(first)


def get_amazon_price(part_name: str, amazon_key: str | None = None) -> dict[str, Any] | None:
    """
    Look up a rough Amazon price for a part name using Rainforest search.

    Uses ``amazon_key`` when non-empty; otherwise the environment variable
    :data:`RAINFOREST_API_KEY_ENV` (``RAINFOREST_API_KEY``). If no key is available
    or search fails, returns ``None``.

    Returns:
        ``{"source": "amazon", "price": int, "title": str}`` on success, else ``None``.
    """
    api_key = (amazon_key or "").strip() or os.environ.get(RAINFOREST_API_KEY_ENV, "").strip()
    if not api_key:
        return None

    out = search_amazon(part_name, api_key)
    if out is None:
        return None

    price, title = out
    return {"source": "amazon", "price": price, "title": title}
