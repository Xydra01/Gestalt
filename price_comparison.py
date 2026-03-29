"""
Combine live Amazon (Rainforest) and eBay (ScrapingBee) prices for PC parts.

Uses :func:`amazon_api.get_amazon_price` and :func:`ebay_api.get_ebay_price`.
All entry points are defensive: exceptions from dependencies are swallowed.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from amazon_api import get_amazon_price
from ebay_api import get_ebay_price

_UNAVAILABLE_NOTE = "unavailable"


def _safe_amazon(part_name: str, amazon_key: str) -> dict[str, Any] | None:
    try:
        return get_amazon_price(part_name, amazon_key)
    except Exception:
        return None


def _safe_ebay(part_name: str, scrapingbee_key: str) -> dict[str, Any] | None:
    try:
        return get_ebay_price(part_name, scrapingbee_key)
    except Exception:
        return None


def _amazon_slot(amz: dict[str, Any] | None) -> dict[str, Any]:
    if amz and isinstance(amz.get("price"), int):
        return {
            "price": amz["price"],
            "source": "amazon",
            "available": True,
        }
    return {
        "price": None,
        "source": "amazon",
        "available": False,
        "note": _UNAVAILABLE_NOTE,
    }


def _ebay_slot(eb: dict[str, Any] | None) -> dict[str, Any]:
    if eb and isinstance(eb.get("price"), int):
        out: dict[str, Any] = {
            "price": eb["price"],
            "source": "ebay",
            "available": True,
        }
        if isinstance(eb.get("note"), str):
            out["note"] = eb["note"]
        return out
    return {
        "price": None,
        "source": "ebay",
        "available": False,
        "note": _UNAVAILABLE_NOTE,
    }


def _best_deal_and_savings(
    pa: int | None, pe: int | None
) -> tuple[str | None, int]:
    """Pick cheaper retailer when both prices exist; savings = higher − lower."""
    if pa is not None and pe is not None:
        if pa < pe:
            return "amazon", pe - pa
        if pe < pa:
            return "ebay", pa - pe
        return "amazon", 0
    if pa is not None:
        return "amazon", 0
    if pe is not None:
        return "ebay", 0
    return None, 0


def get_all_prices(
    part_name: str, amazon_key: str, scrapingbee_key: str
) -> dict[str, Any]:
    """
    Fetch Amazon and eBay prices for a single search string.

    Calls :func:`get_amazon_price` and :func:`get_ebay_price` with the given API keys.
    Failures on either side still return a full structure with ``available: False``
    and ``note: "unavailable"`` for that side.

    Returns:
        A dict with ``amazon``, ``ebay``, ``best_deal`` (``\"amazon\"``, ``\"ebay\"``, or
        ``None``), and ``savings`` (difference when both prices exist, else ``0``).

    Note:
        Does not raise: internal errors are treated as unavailable prices.
    """
    name = (part_name or "").strip()
    ak = (amazon_key or "").strip()
    sk = (scrapingbee_key or "").strip()

    amz_raw = _safe_amazon(name, ak) if name else None
    eb_raw = _safe_ebay(name, sk) if name else None

    amazon_slot = _amazon_slot(amz_raw)
    ebay_slot = _ebay_slot(eb_raw)

    pa = amazon_slot["price"] if amazon_slot.get("available") else None
    pe = ebay_slot["price"] if ebay_slot.get("available") else None
    best, savings = _best_deal_and_savings(
        pa if isinstance(pa, int) else None,
        pe if isinstance(pe, int) else None,
    )

    return {
        "amazon": amazon_slot,
        "ebay": ebay_slot,
        "best_deal": best,
        "savings": savings,
    }


def _part_query(part: dict[str, Any]) -> str:
    """Build a search query from a catalog-style part dict."""
    if not isinstance(part, dict):
        return ""
    for key in ("name", "title", "model"):
        v = part.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    pid = part.get("id")
    if isinstance(pid, str) and pid.strip():
        return pid.strip().replace("-", " ")
    return ""


def enrich_build_with_prices(
    build: dict[str, Any], amazon_key: str, scrapingbee_key: str
) -> dict[str, Any]:
    """
    Attach comparison data to each component in a compatibility-style ``build`` dict.

    Expected keys (each value is a part dict): ``cpu``, ``gpu``, ``motherboard``,
    ``ram``, ``psu``, ``case``. Other keys are copied through. Each part dict gains a
    ``price_comparison`` field from :func:`get_all_prices` for that part's ``name``
    (or ``title`` / ``id`` fallback). Empty queries yield all-unavailable slots.

    Returns:
        A new dict (deep copy of parts) with ``price_comparison`` added per known
        component; does not mutate the input.
    """
    slots = ("cpu", "gpu", "motherboard", "ram", "psu", "case")
    out: dict[str, Any] = {}
    for key, val in build.items():
        if key in slots and isinstance(val, dict):
            q = _part_query(val)
            merged = deepcopy(val)
            merged["price_comparison"] = get_all_prices(q, amazon_key, scrapingbee_key)
            out[key] = merged
        else:
            out[key] = deepcopy(val) if isinstance(val, dict) else val
    return out
