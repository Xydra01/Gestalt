"""

─── Explicit Rule Registry ───────────────────────────────────────────────────
These are the load-bearing compatibility rules for the validation engine.
Encoded as data so they are auditable without reading function logic.
Deterministic compatibility checks for a PC building assistant.

"""

from __future__ import annotations

from typing import Any


def check_cpu_motherboard(cpu: dict[str, Any], mobo: dict[str, Any]) -> bool:
    """
    Return True if the CPU socket matches the motherboard socket.

    Compares ``cpu["socket"]`` to ``mobo["socket"]`` for equality.
    """
    return cpu["socket"] == mobo["socket"]


def check_ram_motherboard(ram: dict[str, Any], mobo: dict[str, Any]) -> bool:
    """
    Return True if RAM generation is supported by the motherboard.

    If ``mobo["ddr_support"]`` is the literal ``"DDR4/DDR5"``, RAM must be
    ``DDR4`` or ``DDR5``. Otherwise ``ram["ddr_gen"]`` must equal
    ``mobo["ddr_support"]``.
    """
    ddr_support = mobo["ddr_support"]
    if ddr_support == "DDR4/DDR5":
        return ram["ddr_gen"] in ("DDR4", "DDR5")
    return ram["ddr_gen"] == ddr_support


def check_psu_wattage(build: dict[str, Any]) -> bool:
    """
    Return True if the PSU has enough headroom for the build.

    ``build`` must include keys: ``cpu``, ``gpu``, ``motherboard``, ``ram``,
    ``psu``, ``case`` (only ``cpu``, ``gpu``, and ``psu`` are used for this check).

    Estimated load = CPU TDP + GPU TDP + 50 W (motherboard) + 10 W (RAM).
    Passes when ``psu["wattage"]`` is at least that total plus 150 W margin.
    """
    cpu = build["cpu"]
    gpu = build["gpu"]
    psu = build["psu"]
    # Fixed allowances for platform and memory (per product spec).
    total = cpu["tdp"] + gpu["tdp"] + 50 + 10
    return psu["wattage"] >= total + 150


def check_gpu_case(gpu: dict[str, Any], case: dict[str, Any]) -> bool:
    """
    Return True if the GPU fits within the case's maximum GPU length.

    Passes when ``gpu["length_mm"]`` is less than or equal to
    ``case["max_gpu_length_mm"]``.
    """
    return gpu["length_mm"] <= case["max_gpu_length_mm"]


def validate_build(build: dict[str, Any]) -> dict[str, Any]:
    """
    Run socket, RAM, PSU, and GPU clearance checks on a full build dict.

    ``build`` must contain: ``cpu``, ``gpu``, ``motherboard``, ``ram``, ``psu``, ``case``.

    Returns a result with ``passed`` (all checks True) and ``errors``, a list
    of objects with ``code``, ``part``, ``message``, and ``fix`` for each failure.
    """
    errors: list[dict[str, str]] = []

    cpu = build["cpu"]
    mobo = build["motherboard"]
    ram = build["ram"]
    gpu = build["gpu"]
    case = build["case"]

    if not check_cpu_motherboard(cpu, mobo):
        errors.append(
            {
                "code": "SOCKET_MISMATCH",
                "part": "motherboard",
                "message": (
                    f"CPU socket {cpu['socket']!r} does not match motherboard socket {mobo['socket']!r}."
                ),
                "fix": "Replace the CPU or the motherboard so both use the same socket.",
            }
        )

    if not check_ram_motherboard(ram, mobo):
        errors.append(
            {
                "code": "RAM_GEN_MISMATCH",
                "part": "ram",
                "message": (
                    f"RAM is {ram['ddr_gen']}, but the motherboard supports {mobo['ddr_support']}."
                ),
                "fix": "Use RAM whose DDR generation matches the motherboard, or pick a board that supports your RAM.",
            }
        )

    if not check_psu_wattage(build):
        # Recompute for a clear message (same formula as check_psu_wattage).
        load = cpu["tdp"] + gpu["tdp"] + 50 + 10
        required = load + 150
        errors.append(
            {
                "code": "INSUFFICIENT_POWER",
                "part": "psu",
                "message": (
                    f"Estimated load ~{load} W (with margin need ≥{required} W); "
                    f"PSU is {build['psu']['wattage']} W."
                ),
                "fix": f"Choose a PSU rated at {required} W or higher (or reduce CPU/GPU power draw).",
            }
        )

    if not check_gpu_case(gpu, case):
        errors.append(
            {
                "code": "GPU_CLEARANCE_FAIL",
                "part": "gpu",
                "message": (
                    f"GPU length {gpu['length_mm']} mm exceeds case limit {case['max_gpu_length_mm']} mm."
                ),
                "fix": "Use a shorter GPU or a case with a larger max GPU length.",
            }
        )

    return {"passed": len(errors) == 0, "errors": errors}
