"""
Amazon product search via Rainforest API (hackathon / demo).

Uses the public request endpoint with ``type=search``. Requires a valid API key
from https://www.rainforestapi.com/
"""

from __future__ import annotations

import json
import os
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus, urlencode
from urllib.request import Request, urlopen

# Environment variable used by :func:`get_amazon_price` when no key is passed in code.
RAINFOREST_API_KEY_ENV = "RAINFOREST_API_KEY"
SERPER_API_KEY_ENV = "SERPER_API_KEY"

_RAINFOREST_REQUEST_URL = "https://api.rainforestapi.com/request"
_REQUEST_TIMEOUT_SEC = 3
_SERPER_SEARCH_URL = "https://google.serper.dev/search"


def _amazon_search_fallback_url(query: str) -> str:
    """Public Amazon search URL when the API does not return a product link."""
    return f"https://www.amazon.com/s?k={quote_plus((query or "").strip())}"


def _extract_product_link(product: dict[str, Any]) -> str | None:
    for k in ("link", "url", "product_url", "product_link"):
        v = product.get(k)
        if isinstance(v, str) and v.strip().startswith("http"):
            return v.strip()
    return None


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


def search_amazon(query: str, api_key: str) -> tuple[int, str, str] | None:
    """
    Search Amazon via Rainforest API and return the first organic result's price, title,
    and product or search URL.

    Calls ``GET https://api.rainforestapi.com/request`` with ``api_key``, ``type=search``,
    and ``search_term`` set to ``query``. Uses a 3-second socket timeout.

    Returns:
        ``(price, title, url)`` where ``url`` is a product link when the API provides one,
        otherwise a fallback Amazon search URL for ``query``. ``None`` if the request fails
        or the first hit has no usable price/title.

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
            "amazon_domain": "amazon.com",
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

    pt = _extract_first_result_price_title(first)
    if pt is None:
        return None
    price, title = pt
    link = _extract_product_link(first) or _amazon_search_fallback_url(query)
    return (price, title, link)


def get_amazon_price(part_name: str, amazon_key: str | None = None) -> dict[str, Any] | None:
    """
    Look up a rough Amazon price for a part name using Rainforest search.

    Uses ``amazon_key`` when non-empty; otherwise the environment variable
    :data:`RAINFOREST_API_KEY_ENV` (``RAINFOREST_API_KEY``). If no key is available
    or search fails, returns ``None``.

    Returns:
        ``{"source": "amazon", "price": int, "title": str, "url": str}`` on success,
        else ``None``.
    """
    api_key = (amazon_key or "").strip() or os.environ.get(RAINFOREST_API_KEY_ENV, "").strip()
    if api_key:
        out = search_amazon(part_name, api_key)
        if out is None:
            return None
        price, title, url = out
        return {"source": "amazon", "price": price, "title": title, "url": url}

    # Fallback for demos: if Rainforest isn't configured, try Serper (Google Search API)
    # to find an Amazon result and a rough price from the snippet when present.
    serper_key = os.environ.get(SERPER_API_KEY_ENV, "").strip()
    if not serper_key:
        return None

    out2 = search_amazon_via_serper(part_name, serper_key)
    if out2 is None:
        return None
    price, title, url = out2
    return {"source": "amazon", "price": price, "title": title, "url": url}


def _extract_price_from_snippet(text: str) -> int | None:
    if not text or not isinstance(text, str):
        return None
    # Common snippet patterns: "$129.99", "$129", "from $129.99"
    m = re.search(r"\$\s*([0-9][0-9,]*)(?:\.(\d{1,2}))?", text)
    if not m:
        return None
    whole = m.group(1).replace(",", "")
    frac = m.group(2) or "0"
    try:
        return int(round(float(f"{whole}.{frac}")))
    except ValueError:
        return None


def search_amazon_via_serper(query: str, api_key: str) -> tuple[int, str, str] | None:
    """
    Fallback Amazon lookup using Serper (Google Search API).

    This is less reliable than Rainforest (snippets may omit prices), but it provides:
    - a likely Amazon URL
    - a rough whole-dollar price when the snippet contains one
    """
    if not (query and str(query).strip() and api_key and str(api_key).strip()):
        return None

    payload = json.dumps(
        {
            "q": f"{query.strip()} site:amazon.com",
            "num": 5,
        }
    ).encode("utf-8")

    try:
        req = Request(
            _SERPER_SEARCH_URL,
            data=payload,
            headers={
                "X-API-KEY": api_key.strip(),
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
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

    organic = data.get("organic")
    if not isinstance(organic, list) or not organic:
        return None

    for item in organic:
        if not isinstance(item, dict):
            continue
        link = item.get("link")
        title = item.get("title")
        snippet = item.get("snippet") or ""
        if not (isinstance(link, str) and link.startswith("http") and "amazon." in link):
            continue
        if not isinstance(title, str) or not title.strip():
            continue
        price = _extract_price_from_snippet(snippet) or 0
        return (int(price), title.strip(), link.strip())

    return None
