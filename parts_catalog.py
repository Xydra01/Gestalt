"""
Load the PC parts catalog: prefer a live URL, then bundled JSON, then a tiny embedded mock.

Primary source is ``PARTS_CATALOG_URL`` (HTTP/HTTPS JSON). When that is unset or fails,
we fall back to ``parts.json`` next to this package. Logging records which path was used.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parent

PARTS_CATALOG_URL_ENV = "PARTS_CATALOG_URL"
_FALLBACK_FILENAME = "parts.json"
_REMOTE_TIMEOUT_SEC = 15

# Returned as the second element of :func:`load_parts_catalog` for callers / UI.
SOURCE_REMOTE = "remote_url"
SOURCE_LOCAL_JSON = "local_json"
SOURCE_EMBEDDED_MOCK = "embedded_mock"


def _embedded_minimal_catalog() -> dict[str, Any]:
    """Last-resort catalog when no remote data and no readable local file."""
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
        1. Remote JSON from ``PARTS_CATALOG_URL`` (if set).
        2. Local ``parts.json`` in the package directory.
        3. Embedded minimal dict (offline / missing file).

    Returns:
        ``(catalog_dict, source)`` where ``source`` is one of
        :data:`SOURCE_REMOTE`, :data:`SOURCE_LOCAL_JSON`, :data:`SOURCE_EMBEDDED_MOCK`.
    """
    url = (os.environ.get(PARTS_CATALOG_URL_ENV) or "").strip()
    if url:
        try:
            req = Request(url, headers={"Accept": "application/json", "User-Agent": "Gestalt/0.1"})
            with urlopen(req, timeout=_REMOTE_TIMEOUT_SEC) as resp:
                body = resp.read().decode("utf-8")
            data: Any = json.loads(body)
            if _looks_like_pc_catalog(data):
                logger.info("Loaded parts catalog from live URL: %s", url)
                return data, SOURCE_REMOTE
            logger.warning(
                "Live catalog URL %s returned JSON that is not a valid PC parts catalog; "
                "falling back to local file %s",
                url,
                _FALLBACK_FILENAME,
            )
        except Exception as e:
            logger.warning(
                "Could not load live parts catalog from %s (%s); falling back to local file %s",
                url,
                e,
                _FALLBACK_FILENAME,
            )
    else:
        logger.info(
            "%s is not set — using local bundled catalog %s (set this env var for a live JSON endpoint)",
            PARTS_CATALOG_URL_ENV,
            _FALLBACK_FILENAME,
        )

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

    logger.warning("Using embedded minimal parts catalog (no usable live or local catalog)")
    return _embedded_minimal_catalog(), SOURCE_EMBEDDED_MOCK
