"""Load `parts.json` and evaluate capability requirements within workspaces."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_parts_document(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    with p.open(encoding="utf-8") as f:
        return json.load(f)


def _missing_for_subset(part_ids: list[str], parts_map: dict[str, dict[str, Any]]) -> list[str]:
    issues: list[str] = []
    subset = list(part_ids)
    for pid in subset:
        if pid not in parts_map:
            issues.append(f"Unknown part id in workspace: {pid!r}")
            continue
        part = parts_map[pid]
        for req in part.get("requires", []) or []:
            satisfied = any(
                req in (parts_map[oid].get("provides") or [])
                for oid in subset
                if oid != pid and oid in parts_map
            )
            if not satisfied:
                issues.append(
                    f"Part {pid!r} requires capability {req!r}, but no other part "
                    f"in this workspace provides it."
                )
    return issues


def evaluate_catalog(doc: dict[str, Any]) -> dict[str, Any]:
    """Check each part's requirements against the full catalog."""
    parts_list = doc.get("parts") or []
    parts_map = {p["id"]: p for p in parts_list if "id" in p}
    all_ids = list(parts_map.keys())
    issues = _missing_for_subset(all_ids, parts_map)
    return {
        "scope": "full_catalog",
        "ok": len(issues) == 0,
        "issues": issues,
        "part_count": len(parts_map),
    }


def evaluate_workspaces(doc: dict[str, Any]) -> list[dict[str, Any]]:
    """Check named subsets (workspaces) for internal compatibility."""
    parts_list = doc.get("parts") or []
    parts_map = {p["id"]: p for p in parts_list if "id" in p}
    results: list[dict[str, Any]] = []
    for ws in doc.get("workspaces") or []:
        name = ws.get("name", "unnamed")
        ids = ws.get("part_ids") or []
        issues = _missing_for_subset(ids, parts_map)
        results.append(
            {
                "name": name,
                "part_ids": ids,
                "ok": len(issues) == 0,
                "issues": issues,
            }
        )
    return results


def summarize(doc: dict[str, Any]) -> dict[str, Any]:
    """Single structure for the web UI and tests."""
    catalog = evaluate_catalog(doc)
    workspaces = evaluate_workspaces(doc)
    return {"catalog": catalog, "workspaces": workspaces}
