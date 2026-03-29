"""
Combine live Amazon (Rainforest) and market pricing (SerpApi) for PC parts.

Uses :func:`amazon_api.get_amazon_price` and :func:`ebay_api.get_ebay_price`.
All entry points are defensive: exceptions from dependencies are swallowed.

Feature map (master plan → code):
- Live pricing enrichment: :func:`enrich_crew_payload_with_pricing`
- Per-part comparison blob: :func:`enrich_build_with_prices` adds ``price_comparison`` on slots
- Rollups displayed in UI: :func:`rollup_pricing`

Reality note:
- The field name ``ebay`` is kept for API/UI compatibility, but the current implementation
  in `ebay_api.py` uses SerpApi Google Shopping rather than scraping eBay HTML.
"""

from __future__ import annotations

import os
from copy import deepcopy
from typing import Any

from amazon_api import get_amazon_price
from ebay_api import get_ebay_price

_UNAVAILABLE_NOTE = "unavailable"

# Typical system-integrator / boutique assembly margin on parts (env override).
_BUILD_SERVICE_RATE_ENV = "GESTALT_PC_BUILD_SERVICE_RATE"

_BUILD_SLOTS = ("cpu", "gpu", "motherboard", "ram", "psu", "case")


def _build_service_rate() -> float:
    raw = (os.environ.get(_BUILD_SERVICE_RATE_ENV) or "").strip()
    if not raw:
        return 0.12
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 0.12


def _safe_amazon(part_name: str, amazon_key: str) -> dict[str, Any] | None:
    try:
        return get_amazon_price(part_name, amazon_key)
    except Exception:
        return None


def _safe_ebay(part_name: str, serpapi_key: str) -> dict[str, Any] | None:
    try:
        return get_ebay_price(part_name, serpapi_key)
    except Exception:
        return None


def _amazon_slot(amz: dict[str, Any] | None) -> dict[str, Any]:
    if amz and isinstance(amz.get("price"), int):
        out: dict[str, Any] = {
            "price": amz["price"],
            "source": "amazon",
            "available": True,
        }
        if isinstance(amz.get("url"), str) and amz["url"].strip():
            out["url"] = amz["url"].strip()
        if isinstance(amz.get("title"), str):
            out["title"] = amz["title"]
        return out
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
        if isinstance(eb.get("url"), str) and eb["url"].strip():
            out["url"] = eb["url"].strip()
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


def _effective_price_and_basis(
    pa: int | None,
    pe: int | None,
    best: str | None,
    catalog_price: float | None,
) -> tuple[float | None, str]:
    """Best live price when available; otherwise catalog."""
    if pa is not None and pe is not None:
        return float(min(pa, pe)), "live"
    if pa is not None:
        return float(pa), "live"
    if pe is not None:
        return float(pe), "live"
    if catalog_price is not None:
        return float(catalog_price), "catalog"
    return None, "none"


def _best_url(
    best: str | None, pa: int | None, pe: int | None, amazon_slot: dict, ebay_slot: dict
) -> str | None:
    if best == "amazon" and pa is not None:
        u = amazon_slot.get("url")
        return u if isinstance(u, str) else None
    if best == "ebay" and pe is not None:
        u = ebay_slot.get("url")
        return u if isinstance(u, str) else None
    if pa is not None:
        u = amazon_slot.get("url")
        return u if isinstance(u, str) else None
    if pe is not None:
        u = ebay_slot.get("url")
        return u if isinstance(u, str) else None
    return None


def get_all_prices(
    part_name: str,
    amazon_key: str,
    serpapi_key: str,
    *,
    catalog_price: float | None = None,
) -> dict[str, Any]:
    """
    Fetch Amazon and eBay prices for a single search string.

    When both live prices exist, ``savings`` is the spread (what you save vs the
    pricier retailer). ``effective_price`` prefers the cheaper live price, else
    ``catalog_price``.

    Returns:
        Structure with ``amazon``, ``ebay``, ``best_deal``, ``savings``,
        ``effective_price``, ``price_basis``, ``best_url``, and ``catalog_price``.
    """
    name = (part_name or "").strip()
    ak = (amazon_key or "").strip()
    sk = (serpapi_key or "").strip()

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
    eff, basis = _effective_price_and_basis(
        pa if isinstance(pa, int) else None,
        pe if isinstance(pe, int) else None,
        best,
        catalog_price,
    )
    burl = _best_url(best, pa, pe, amazon_slot, ebay_slot)

    return {
        "amazon": amazon_slot,
        "ebay": ebay_slot,
        "best_deal": best,
        "savings": savings,
        "effective_price": eff,
        "price_basis": basis,
        "best_url": burl,
        "catalog_price": catalog_price,
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


def _catalog_price(part: dict[str, Any]) -> float | None:
    p = part.get("price")
    if isinstance(p, (int, float)):
        return float(p)
    return None


def enrich_build_with_prices(
    build: dict[str, Any], amazon_key: str, serpapi_key: str
) -> dict[str, Any]:
    """
    Attach comparison data to each component in a compatibility-style ``build`` dict.

    Each part dict gains a ``price_comparison`` field from :func:`get_all_prices`.
    """
    out: dict[str, Any] = {}
    for key, val in build.items():
        if key in _BUILD_SLOTS and isinstance(val, dict):
            q = _part_query(val)
            cat = _catalog_price(val)
            merged = deepcopy(val)
            merged["price_comparison"] = get_all_prices(
                q, amazon_key, serpapi_key, catalog_price=cat
            )
            out[key] = merged
        else:
            out[key] = deepcopy(val) if isinstance(val, dict) else val
    return out


def rollup_pricing(enriched_build: dict[str, Any]) -> dict[str, Any]:
    """
    Aggregate catalog totals, live-best totals, cross-retailer savings, and an
    estimated savings line: (sum of retailer spreads) + (build-service rate × total).

    ``estimated_savings_total`` is intended for UI as "what you kept vs paying more
    elsewhere + typical builder fee."
    """
    total_catalog = 0.0
    total_effective = 0.0
    cross = 0
    any_live = False

    for slot in _BUILD_SLOTS:
        p = enriched_build.get(slot)
        if not isinstance(p, dict):
            continue
        comp = p.get("price_comparison")
        if not isinstance(comp, dict):
            continue
        cat = comp.get("catalog_price")
        if isinstance(cat, (int, float)):
            total_catalog += float(cat)

        eff = comp.get("effective_price")
        if isinstance(eff, (int, float)):
            total_effective += float(eff)
        elif isinstance(cat, (int, float)):
            total_effective += float(cat)

        if comp.get("price_basis") == "live":
            any_live = True
        cross += int(comp.get("savings") or 0)

    rate = _build_service_rate()
    build_fee_savings = round(total_effective * rate)
    estimated_total = cross + build_fee_savings

    return {
        "total_parts": round(total_effective, 2),
        "total_catalog": round(total_catalog, 2),
        "cross_retailer_savings": cross,
        "build_service_savings_estimate": build_fee_savings,
        "estimated_savings_total": estimated_total,
        "build_fee_rate_applied": rate,
        "pricing_basis": "live_mixed" if any_live else "catalog_only",
    }


def enrich_crew_payload_with_pricing(payload: dict[str, Any]) -> dict[str, Any]:
    """
    After a successful crew run, merge live/catalog pricing into the payload.

    Overwrites ``total`` with ``pricing.total_parts`` (live-aware) and ``savings``
    with ``pricing.estimated_savings_total`` when rollup succeeds.
    """
    if not payload.get("success"):
        return payload
    build = payload.get("build")
    if not isinstance(build, dict):
        return payload

    amazon_key = (os.environ.get("RAINFOREST_API_KEY") or "").strip()
    serpapi_key = (os.environ.get("SERPAPI_API_KEY") or "").strip()

    enriched = enrich_build_with_prices(build, amazon_key, serpapi_key)
    pricing = rollup_pricing(enriched)

    out = {**payload, "build": enriched, "pricing": pricing}
    out["total"] = pricing["total_parts"]
    out["savings"] = pricing["estimated_savings_total"]
    return out
