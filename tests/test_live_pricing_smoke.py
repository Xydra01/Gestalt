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
import requests
from dotenv import load_dotenv

from amazon_api import RAINFOREST_API_KEY_ENV, SERPER_API_KEY_ENV, get_amazon_price, search_amazon
from ebay_api import SERPAPI_API_KEY_ENV, get_ebay_price, scrape_ebay_price


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

    # If an adapter returns None, print a minimal, non-secret diagnostic showing which key paths
    # are configured and whether the lower-level helpers can produce a result.
    if amz is None and has_amazon:
        has_rainforest = bool(os.environ.get(RAINFOREST_API_KEY_ENV))
        has_serper = bool(os.environ.get(SERPER_API_KEY_ENV))
        print("\namazon diag:")
        print(
            "configured:",
            {"rainforest": has_rainforest, "serper_fallback": has_serper},
        )
        if has_rainforest:
            tup = search_amazon(part_name, os.environ.get(RAINFOREST_API_KEY_ENV, ""))
            print("search_amazon ->", json.dumps(_redact(tup), indent=2))
            if tup is None:
                # Print minimal HTTP diagnostics (status + short body prefix).
                # Do NOT print the API key. We pass it in params but redact it from output.
                try:
                    resp = requests.get(
                        "https://api.rainforestapi.com/request",
                        params={
                            "api_key": os.environ.get(RAINFOREST_API_KEY_ENV, ""),
                            "type": "search",
                            "amazon_domain": "amazon.com",
                            "search_term": part_name,
                        },
                        headers={"Accept": "application/json"},
                        timeout=3,
                    )
                    body = (resp.text or "")[:600]
                    body = body.replace(os.environ.get(RAINFOREST_API_KEY_ENV, ""), "***REDACTED***")
                    print("rainforest_http:", {"status_code": resp.status_code})
                    print("rainforest_body_prefix:", body)
                except Exception as e:
                    print("rainforest_http_error:", type(e).__name__, str(e))
    if shp is None and has_serpapi:
        print("\nshopping diag:")
        print("configured:", {"serpapi": bool(os.environ.get(SERPAPI_API_KEY_ENV))})
        raw_price = scrape_ebay_price(part_name, os.environ.get(SERPAPI_API_KEY_ENV, ""))
        print("scrape_ebay_price ->", json.dumps(_redact(raw_price), indent=2))
        if raw_price is None:
            try:
                resp = requests.get(
                    "https://serpapi.com/search.json",
                    params={
                        "api_key": os.environ.get(SERPAPI_API_KEY_ENV, ""),
                        "engine": "google_shopping",
                        "q": part_name,
                        "no_cache": "true",
                    },
                    timeout=3,
                )
                body = (resp.text or "")[:900]
                body = body.replace(os.environ.get(SERPAPI_API_KEY_ENV, ""), "***REDACTED***")
                print("serpapi_http:", {"status_code": resp.status_code})
                print("serpapi_body_prefix:", body)
            except Exception as e:
                print("serpapi_http_error:", type(e).__name__, str(e))

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

