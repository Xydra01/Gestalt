"""
Integration smoke test for live pricing adapters.

Purpose:
- Exercise the *real* retailer APIs using locally configured API keys.
- Print the raw response objects so we can spot malformed / unexpected shapes.

How to run (prints to console):
    python3 -m pytest -m integration -s tests/test_live_pricing_smoke.py

Notes:
- This test is intentionally NOT CI-friendly and is marked `integration`.
- It must never print API keys. We only print the adapter return dicts (price/title/url/note).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest
from dotenv import load_dotenv

from amazon_api import get_amazon_price
from ebay_api import get_ebay_price


def _redact(obj: Any) -> Any:
    """
    Best-effort redaction for debug printing.

    We do NOT expect keys in adapter outputs, but this prevents accidental leakage if an upstream
    library ever echoes config fields.
    """
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            lk = str(k).lower()
            if "key" in lk or "token" in lk or "secret" in lk:
                out[k] = "***REDACTED***"
            else:
                out[k] = _redact(v)
        return out
    if isinstance(obj, list):
        return [_redact(x) for x in obj]
    return obj


@pytest.mark.integration
def test_live_pricing_adapters_print_raw_responses() -> None:
    # Load local .env for dev runs (never committed). If the runner already set env vars, this is a no-op.
    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)

    # We can run with either Rainforest or Serper for Amazon; and SerpApi for shopping ("eBay") prices.
    has_amazon = bool(os.environ.get("RAINFOREST_API_KEY") or os.environ.get("SERPER_API_KEY"))
    has_serpapi = bool(os.environ.get("SERPAPI_API_KEY"))
    if not has_amazon and not has_serpapi:
        pytest.skip("No pricing keys configured (set RAINFOREST_API_KEY/SERPER_API_KEY and/or SERPAPI_API_KEY).")

    # Pick a stable query string (doesn't have to match catalog IDs).
    part_name = "AMD Ryzen 5 7600"

    amz = get_amazon_price(part_name)
    shp = get_ebay_price(part_name)

    print("\n=== LIVE PRICING SMOKE ===")
    print("keys_present:", {"amazon": has_amazon, "serpapi": has_serpapi})
    print("query:", part_name)
    print("amazon_api.get_amazon_price ->")
    print(json.dumps(_redact(amz), indent=2, sort_keys=True))
    print("ebay_api.get_ebay_price (SerpApi Google Shopping) ->")
    print(json.dumps(_redact(shp), indent=2, sort_keys=True))

    # Basic shape sanity checks (helps catch damaged/misformatted output early).
    if has_amazon:
        assert amz is None or (isinstance(amz, dict) and amz.get("source") == "amazon")
        if isinstance(amz, dict):
            assert "price" in amz
            assert "url" in amz
    if has_serpapi:
        assert shp is None or (isinstance(shp, dict) and shp.get("source") == "ebay")
        if isinstance(shp, dict):
            assert "price" in shp
            assert "url" in shp

