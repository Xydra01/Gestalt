"""
Load the PC parts catalog from bundled ``parts.json``, with a tiny embedded fallback.

Live **prices** for picked parts come from Amazon/eBay in :mod:`price_comparison`, using
catalog ``price`` when live data is unavailable — there is no remote catalog JSON.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parent

_FALLBACK_FILENAME = "parts.json"

# Returned as the second element of :func:`load_parts_catalog` for callers / UI.
SOURCE_LOCAL_JSON = "local_json"
SOURCE_EMBEDDED_MOCK = "embedded_mock"


def _embedded_minimal_catalog() -> dict[str, Any]:
    """Last-resort catalog when the bundled file is missing or invalid."""
    return {
        "cpus": [{"id": "c1", "price": 200, "socket": "AM5", "tdp": 105}],
        "gpus": [{"id": "g1", "price": 400, "tdp": 200, "length_mm": 300}],
        "motherboards": [{"id": "m1", "price": 150, "socket": "AM5", "ddr_support": "DDR5"}],
        "ram": [{"id": "r1", "price": 80, "ddr_gen": "DDR5"}],
        "psus": [{"id": "p1", "price": 100, "wattage": 750}],
        "cases": [{"id": "case1", "price": 90, "max_gpu_length_mm": 350}],
    }


def _looks_like_pc_catalog(data: Any) -> bool:
    if not isinstance(data, dict):
        return False
    keys = ("cpus", "gpus", "motherboards", "ram", "psus", "cases")
    return any(isinstance(data.get(k), list) for k in keys)


def load_parts_catalog() -> tuple[dict[str, Any], str]:
    """
    Load parts data for agents and validation.

    Order:
        1. Local ``parts.json`` in the package directory.
        2. Embedded minimal dict (missing/unreadable file).

    Returns:
        ``(catalog_dict, source)`` where ``source`` is :data:`SOURCE_LOCAL_JSON` or
        :data:`SOURCE_EMBEDDED_MOCK`.
    """
    path = _ROOT / _FALLBACK_FILENAME
    if path.is_file():
        try:
            with path.open(encoding="utf-8") as f:
                data = json.load(f)
            if _looks_like_pc_catalog(data):
                logger.info("Loaded parts catalog from local file %s", path)
                return data, SOURCE_LOCAL_JSON
            logger.warning(
                "Local file %s is not a valid PC parts catalog shape; using embedded minimal catalog",
                path,
            )
        except (OSError, json.JSONDecodeError) as e:
            logger.warning(
                "Failed to read local catalog %s: %s — using embedded minimal catalog",
                path,
                e,
            )
    else:
        logger.warning(
            "Local catalog file %s not found — using embedded minimal catalog",
            path,
        )

    logger.warning("Using embedded minimal parts catalog (no readable %s)", _FALLBACK_FILENAME)
    return _embedded_minimal_catalog(), SOURCE_EMBEDDED_MOCK
