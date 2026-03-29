"""Unit tests for conflict_resolver (typed single-slot substitutions)."""

from __future__ import annotations

from conflict_resolver import resolve_conflict


def _budget() -> dict[str, float]:
    return {
        "gpu": 500.0,
        "cpu": 300.0,
        "mobo": 200.0,
        "ram": 150.0,
        "psu": 200.0,
        "case": 100.0,
    }


def test_resolve_psu_upgrades_to_cheapest_meeting_wattage() -> None:
    catalog = {
        "psus": [
            {"id": "weak-500", "price": 40, "wattage": 500},
            {"id": "ok-750a", "price": 120, "wattage": 750},
            {"id": "ok-750b", "price": 115, "wattage": 750},
            {"id": "overkill-1200", "price": 199, "wattage": 1200},
        ]
    }
    # need = 125 + 400 + 50 + 10 + 150 = 735
    build = {
        "cpu": {"id": "c", "tdp": 125, "socket": "AM5"},
        "gpu": {"id": "g", "tdp": 400, "length_mm": 250, "tier": "mid"},
        "motherboard": {"id": "m", "socket": "AM5", "ddr_support": "DDR5"},
        "ram": {"id": "r", "ddr_gen": "DDR5"},
        "psu": {"id": "weak-500", "price": 40, "wattage": 500},
        "case": {"id": "case", "max_gpu_length_mm": 400},
    }
    patched, meta = resolve_conflict(
        "INSUFFICIENT_POWER", build, catalog, _budget(), None
    )
    assert patched is not None and meta is not None
    assert patched["psu"]["id"] == "ok-750b"
    assert meta["slot"] == "psu"
    assert meta["strategy"] == "PSU_UNDERPOWERED"


def test_resolve_psu_returns_none_when_nothing_fits_envelope() -> None:
    catalog = {
        "psus": [
            {"id": "weak", "price": 40, "wattage": 500},
        ]
    }
    build = {
        "cpu": {"id": "c", "tdp": 200, "socket": "AM5"},
        "gpu": {"id": "g", "tdp": 400, "length_mm": 250, "tier": "high"},
        "motherboard": {"id": "m", "socket": "AM5", "ddr_support": "DDR5"},
        "ram": {"id": "r", "ddr_gen": "DDR5"},
        "psu": {"id": "weak", "price": 40, "wattage": 500},
        "case": {"id": "case", "max_gpu_length_mm": 400},
    }
    patched, meta = resolve_conflict(
        "INSUFFICIENT_POWER", build, catalog, {"psu": 50.0}, None
    )
    assert patched is None and meta is None


def test_resolve_motherboard_matches_cpu_socket() -> None:
    catalog = {
        "motherboards": [
            {"id": "wrong-lga", "price": 100, "socket": "LGA1700", "ddr_support": "DDR5"},
            {"id": "ok-am5-cheap", "price": 120, "socket": "AM5", "ddr_support": "DDR5"},
            {"id": "ok-am5-costly", "price": 200, "socket": "AM5", "ddr_support": "DDR5"},
        ]
    }
    build = {
        "cpu": {"id": "c", "tdp": 65, "socket": "AM5"},
        "gpu": {"id": "g", "tdp": 200, "length_mm": 250, "tier": "mid"},
        "motherboard": {"id": "wrong-lga", "socket": "LGA1700", "ddr_support": "DDR5"},
        "ram": {"id": "r", "ddr_gen": "DDR5"},
        "psu": {"id": "p", "price": 80, "wattage": 850},
        "case": {"id": "case", "max_gpu_length_mm": 400},
    }
    patched, meta = resolve_conflict(
        "SOCKET_MISMATCH", build, catalog, _budget(), None
    )
    assert patched is not None and meta is not None
    assert patched["motherboard"]["id"] == "ok-am5-cheap"
    assert meta["slot"] == "motherboard"


def test_resolve_ram_ddr_matches_board() -> None:
    catalog = {
        "ram": [
            {"id": "ddr4-kit", "price": 60, "ddr_gen": "DDR4"},
            {"id": "ddr5-kit", "price": 90, "ddr_gen": "DDR5"},
        ]
    }
    build = {
        "cpu": {"id": "c", "tdp": 65, "socket": "AM5"},
        "gpu": {"id": "g", "tdp": 200, "length_mm": 250, "tier": "mid"},
        "motherboard": {"id": "m", "socket": "AM5", "ddr_support": "DDR5"},
        "ram": {"id": "ddr4-kit", "ddr_gen": "DDR4"},
        "psu": {"id": "p", "price": 80, "wattage": 850},
        "case": {"id": "case", "max_gpu_length_mm": 400},
    }
    patched, meta = resolve_conflict(
        "RAM_GEN_MISMATCH", build, catalog, _budget(), None
    )
    assert patched is not None and meta is not None
    assert patched["ram"]["id"] == "ddr5-kit"
    assert meta["slot"] == "ram"


def test_resolve_gpu_shorter_prefers_shorter_then_cheaper() -> None:
    catalog = {
        "gpus": [
            {"id": "long", "price": 400, "tdp": 200, "length_mm": 340, "tier": "high"},
            {"id": "short-expensive", "price": 500, "tdp": 200, "length_mm": 260, "tier": "high"},
            {"id": "short-cheap", "price": 420, "tdp": 200, "length_mm": 260, "tier": "high"},
        ]
    }
    build = {
        "cpu": {"id": "c", "tdp": 65, "socket": "AM5"},
        "gpu": {
            "id": "long",
            "tdp": 200,
            "length_mm": 340,
            "tier": "high",
        },
        "motherboard": {"id": "m", "socket": "AM5", "ddr_support": "DDR5"},
        "ram": {"id": "r", "ddr_gen": "DDR5"},
        "psu": {"id": "p", "price": 80, "wattage": 850},
        "case": {"id": "case", "max_gpu_length_mm": 300},
    }
    patched, meta = resolve_conflict(
        "GPU_CLEARANCE_FAIL", build, catalog, _budget(), None
    )
    assert patched is not None and meta is not None
    assert patched["gpu"]["id"] == "short-cheap"
    assert meta["slot"] == "gpu"


def test_resolve_unknown_code_returns_none() -> None:
    build = {
        "cpu": {"id": "c", "tdp": 65, "socket": "AM5"},
        "gpu": {"id": "g", "tdp": 200, "length_mm": 250, "tier": "mid"},
        "motherboard": {"id": "m", "socket": "AM5", "ddr_support": "DDR5"},
        "ram": {"id": "r", "ddr_gen": "DDR5"},
        "psu": {"id": "p", "price": 80, "wattage": 850},
        "case": {"id": "case", "max_gpu_length_mm": 400},
    }
    assert resolve_conflict("OTHER", build, {}, _budget(), None) == (None, None)
