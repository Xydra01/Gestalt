"""
Typed substitution strategies for compatibility repair.

Maps ``compatibility_checker`` error codes to single-slot catalog swaps.
Does not call the LLM. Used by :func:`crew.run_build_assistant`.
"""

from __future__ import annotations

import copy
from typing import Any

# Validator codes (compatibility_checker.validate_build) -> strategy labels for traces
CODE_TO_STRATEGY: dict[str, str] = {
    "INSUFFICIENT_POWER": "PSU_UNDERPOWERED",
    "SOCKET_MISMATCH": "SOCKET_MISMATCH",
    "RAM_GEN_MISMATCH": "RAM_INCOMPATIBLE",
    "GPU_CLEARANCE_FAIL": "GPU_CLEARANCE",
}

_TIER_RANK: dict[str, int] = {"budget": 0, "mid": 1, "high": 2}


def _mobo_budget_usd(budget_envelope: dict[str, float]) -> float:
    v = budget_envelope.get("mobo")
    return float(v) if isinstance(v, (int, float)) else float("inf")


def _slot_budget_usd(budget_envelope: dict[str, float], slot: str) -> float:
    key = "mobo" if slot == "motherboard" else slot
    v = budget_envelope.get(key)
    return float(v) if isinstance(v, (int, float)) else float("inf")


def _part_price(part: dict[str, Any]) -> float | None:
    p = part.get("price")
    return float(p) if isinstance(p, (int, float)) else None


def _cheapest(
    rows: list[dict[str, Any]], cap: float
) -> dict[str, Any] | None:
    """Pick lowest price among rows with price <= cap."""
    candidates: list[tuple[float, dict[str, Any]]] = []
    for r in rows:
        pr = _part_price(r)
        if pr is None or pr > cap:
            continue
        candidates.append((pr, r))
    if not candidates:
        return None
    candidates.sort(key=lambda t: t[0])
    return candidates[0][1]


def _required_psu_wattage(build: dict[str, Any]) -> int | None:
    try:
        cpu = build["cpu"]
        gpu = build["gpu"]
        load = int(cpu["tdp"]) + int(gpu["tdp"]) + 50 + 10
        return load + 150
    except (KeyError, TypeError, ValueError):
        return None


def _ram_matches_mobo(ram: dict[str, Any], mobo: dict[str, Any]) -> bool:
    ddr_support = mobo.get("ddr_support")
    gen = ram.get("ddr_gen")
    if not isinstance(ddr_support, str) or not isinstance(gen, str):
        return False
    if ddr_support == "DDR4/DDR5":
        return gen in ("DDR4", "DDR5")
    return gen == ddr_support


def _substitute_psu(
    build: dict[str, Any],
    catalog: dict[str, Any],
    budget_envelope: dict[str, float],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    need = _required_psu_wattage(build)
    if need is None:
        return None, None
    cap = _slot_budget_usd(budget_envelope, "psu")
    rows = catalog.get("psus")
    if not isinstance(rows, list):
        return None, None
    candidates: list[tuple[float, int, dict[str, Any]]] = []
    for p in rows:
        if not isinstance(p, dict):
            continue
        w = p.get("wattage")
        pr = _part_price(p)
        if not isinstance(w, (int, float)) or pr is None:
            continue
        if int(w) >= need and pr <= cap:
            candidates.append((pr, int(w), p))
    if not candidates:
        return None, None
    candidates.sort(key=lambda t: (t[0], t[1]))
    chosen = candidates[0][2]
    prev = build.get("psu")
    out = copy.deepcopy(build)
    out["psu"] = chosen
    meta = {
        "strategy": CODE_TO_STRATEGY["INSUFFICIENT_POWER"],
        "slot": "psu",
        "message": (
            f"PSU_UNDERPOWERED detected: substituting PSU upward to {chosen.get('wattage')} W "
            f"(need ≥{need} W) within ${cap:.0f} PSU envelope"
        ),
        "from_id": prev.get("id") if isinstance(prev, dict) else None,
        "to_id": chosen.get("id"),
        "required_watts": need,
    }
    return out, meta


def _substitute_motherboard(
    build: dict[str, Any],
    catalog: dict[str, Any],
    budget_envelope: dict[str, float],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    cpu = build.get("cpu")
    if not isinstance(cpu, dict):
        return None, None
    sock = cpu.get("socket")
    if not isinstance(sock, str):
        return None, None
    cap = _mobo_budget_usd(budget_envelope)
    rows = catalog.get("motherboards")
    if not isinstance(rows, list):
        return None, None
    matches = [r for r in rows if isinstance(r, dict) and r.get("socket") == sock]
    chosen = _cheapest(matches, cap)
    if chosen is None:
        return None, None
    prev = build.get("motherboard")
    out = copy.deepcopy(build)
    out["motherboard"] = chosen
    # Re-validate RAM against new board if needed (caller may hit RAM_GEN_MISMATCH next)
    meta = {
        "strategy": CODE_TO_STRATEGY["SOCKET_MISMATCH"],
        "slot": "motherboard",
        "message": (
            f"SOCKET_MISMATCH detected: substituting motherboard to match CPU socket {sock!r} "
            f"within ${cap:.0f} motherboard envelope"
        ),
        "from_id": prev.get("id") if isinstance(prev, dict) else None,
        "to_id": chosen.get("id"),
    }
    return out, meta


def _substitute_ram(
    build: dict[str, Any],
    catalog: dict[str, Any],
    budget_envelope: dict[str, float],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    mobo = build.get("motherboard")
    if not isinstance(mobo, dict):
        return None, None
    cap = _slot_budget_usd(budget_envelope, "ram")
    rows = catalog.get("ram")
    if not isinstance(rows, list):
        return None, None
    matches = [r for r in rows if isinstance(r, dict) and _ram_matches_mobo(r, mobo)]
    chosen = _cheapest(matches, cap)
    if chosen is None:
        return None, None
    prev = build.get("ram")
    out = copy.deepcopy(build)
    out["ram"] = chosen
    meta = {
        "strategy": CODE_TO_STRATEGY["RAM_GEN_MISMATCH"],
        "slot": "ram",
        "message": (
            f"RAM_INCOMPATIBLE detected: substituting RAM to match board DDR support "
            f"({mobo.get('ddr_support')}) within ${cap:.0f} RAM envelope"
        ),
        "from_id": prev.get("id") if isinstance(prev, dict) else None,
        "to_id": chosen.get("id"),
    }
    return out, meta


def _substitute_gpu_shorter(
    build: dict[str, Any],
    catalog: dict[str, Any],
    budget_envelope: dict[str, float],
    analysis: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    _ = analysis  # reserved for future tier / use-case tuning
    case = build.get("case")
    gpu = build.get("gpu")
    if not isinstance(case, dict) or not isinstance(gpu, dict):
        return None, None
    max_len = case.get("max_gpu_length_mm")
    if not isinstance(max_len, (int, float)):
        return None, None
    cap = _slot_budget_usd(budget_envelope, "gpu")
    cur_tier = gpu.get("tier")
    cur_rank = _TIER_RANK.get(str(cur_tier), 0)
    rows = catalog.get("gpus")
    if not isinstance(rows, list):
        return None, None

    def _gpu_ok(g: dict[str, Any]) -> bool:
        if not isinstance(g.get("length_mm"), (int, float)):
            return False
        if float(g["length_mm"]) > float(max_len):
            return False
        tr = str(g.get("tier") or "budget")
        if _TIER_RANK.get(tr, 0) < cur_rank:
            return False
        pr = _part_price(g)
        return pr is not None and pr <= cap

    candidates = [g for g in rows if isinstance(g, dict) and _gpu_ok(g)]
    # Prefer shorter length, then cheaper
    scored: list[tuple[float, float, dict[str, Any]]] = []
    for g in candidates:
        pr = _part_price(g) or float("inf")
        ln = float(g.get("length_mm") or 1e9)
        scored.append((ln, pr, g))
    if not scored:
        return None, None
    scored.sort(key=lambda t: (t[0], t[1]))
    chosen = scored[0][2]
    if chosen.get("id") == gpu.get("id"):
        return None, None
    out = copy.deepcopy(build)
    out["gpu"] = chosen
    meta = {
        "strategy": CODE_TO_STRATEGY["GPU_CLEARANCE_FAIL"],
        "slot": "gpu",
        "message": (
            f"GPU_CLEARANCE detected: substituting GPU to {chosen.get('length_mm')} mm length "
            f"(fits case ≤{max_len} mm) within ${cap:.0f} GPU envelope"
        ),
        "from_id": gpu.get("id"),
        "to_id": chosen.get("id"),
    }
    return out, meta


def resolve_conflict(
    error_code: str,
    current_build: dict[str, Any],
    catalog: dict[str, Any],
    budget_envelope: dict[str, float],
    analysis: dict[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """
    Apply a single-slot fix for the given validator error code.

    Returns ``(patched_build, trace_meta)`` or ``(None, None)`` if no substitute exists
    within the per-slot budget envelope.
    """
    if error_code == "INSUFFICIENT_POWER":
        return _substitute_psu(current_build, catalog, budget_envelope)
    if error_code == "SOCKET_MISMATCH":
        return _substitute_motherboard(current_build, catalog, budget_envelope)
    if error_code == "RAM_GEN_MISMATCH":
        return _substitute_ram(current_build, catalog, budget_envelope)
    if error_code == "GPU_CLEARANCE_FAIL":
        return _substitute_gpu_shorter(current_build, catalog, budget_envelope, analysis)
    return None, None
