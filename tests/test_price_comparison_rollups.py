"""Unit tests for pricing rollup (no network)."""

from __future__ import annotations

import os
from unittest.mock import patch

from price_comparison import enrich_crew_payload_with_pricing, rollup_pricing


def test_rollup_catalog_only_sums_build_fee_savings() -> None:
    enriched = {
        "cpu": {
            "price_comparison": {
                "effective_price": 100.0,
                "price_basis": "catalog",
                "catalog_price": 100.0,
                "savings": 0,
            }
        },
        "gpu": {
            "price_comparison": {
                "effective_price": 200.0,
                "price_basis": "catalog",
                "catalog_price": 200.0,
                "savings": 0,
            }
        },
        "motherboard": {"price_comparison": {"effective_price": 0, "price_basis": "catalog", "savings": 0}},
        "ram": {"price_comparison": {"effective_price": 0, "price_basis": "catalog", "savings": 0}},
        "psu": {"price_comparison": {"effective_price": 0, "price_basis": "catalog", "savings": 0}},
        "case": {"price_comparison": {"effective_price": 0, "price_basis": "catalog", "savings": 0}},
    }
    with patch.dict(os.environ, {"GESTALT_PC_BUILD_SERVICE_RATE": "0.10"}):
        r = rollup_pricing(enriched)
    assert r["pricing_basis"] == "catalog_only"
    assert r["total_parts"] == 300.0
    assert r["cross_retailer_savings"] == 0
    assert r["build_service_savings_estimate"] == 30  # 10% of 300
    assert r["estimated_savings_total"] == 30


def test_rollup_live_includes_cross_retailer() -> None:
    enriched = {
        "cpu": {
            "price_comparison": {
                "effective_price": 90.0,
                "price_basis": "live",
                "catalog_price": 100.0,
                "savings": 15,
            }
        },
        "gpu": {"price_comparison": {"effective_price": 0, "price_basis": "catalog", "savings": 0}},
        "motherboard": {"price_comparison": {"effective_price": 0, "price_basis": "catalog", "savings": 0}},
        "ram": {"price_comparison": {"effective_price": 0, "price_basis": "catalog", "savings": 0}},
        "psu": {"price_comparison": {"effective_price": 0, "price_basis": "catalog", "savings": 0}},
        "case": {"price_comparison": {"effective_price": 0, "price_basis": "catalog", "savings": 0}},
    }
    with patch.dict(os.environ, {"GESTALT_PC_BUILD_SERVICE_RATE": "0"}):
        r = rollup_pricing(enriched)
    assert r["pricing_basis"] == "live_mixed"
    assert r["cross_retailer_savings"] == 15
    assert r["estimated_savings_total"] == 15


def test_enrich_payload_overwrites_totals(monkeypatch) -> None:
    monkeypatch.setenv("RAINFOREST_API_KEY", "")
    monkeypatch.setenv("SERPAPI_API_KEY", "")
    payload = {
        "success": True,
        "build": {
            "cpu": {"name": "X", "price": 100},
            "gpu": {"name": "Y", "price": 200},
            "motherboard": {"name": "Z", "price": 0},
            "ram": {"name": "R", "price": 0},
            "psu": {"name": "P", "price": 0},
            "case": {"name": "C", "price": 0},
        },
        "total": 999.0,
        "savings": 1.0,
    }
    out = enrich_crew_payload_with_pricing(payload)
    assert "pricing" in out
    assert out["total"] == out["pricing"]["total_parts"]
    assert out["savings"] == out["pricing"]["estimated_savings_total"]
    assert "price_comparison" in out["build"]["cpu"]
