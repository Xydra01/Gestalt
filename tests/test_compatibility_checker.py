"""Tests for parts.json compatibility evaluation."""

from __future__ import annotations

import json
from pathlib import Path

from compatibility_checker import evaluate_catalog, evaluate_workspaces, load_parts_document, summarize

_ROOT = Path(__file__).resolve().parent.parent


def test_load_parts_document() -> None:
    doc = load_parts_document(_ROOT / "parts.json")
    assert "parts" in doc
    assert len(doc["parts"]) >= 1


def test_full_catalog_ok_for_sample_repo() -> None:
    doc = load_parts_document(_ROOT / "parts.json")
    catalog = evaluate_catalog(doc)
    assert catalog["ok"] is True
    assert catalog["part_count"] == len(doc["parts"])


def test_bad_workspace_flagged() -> None:
    doc = load_parts_document(_ROOT / "parts.json")
    workspaces = evaluate_workspaces(doc)
    bad = next(ws for ws in workspaces if ws["name"] == "bad_combo")
    assert bad["ok"] is False
    assert any("llm" in issue.lower() for issue in bad["issues"])


def test_summarize_shape() -> None:
    doc = json.loads(
        json.dumps(
            {
                "parts": [
                    {"id": "a", "requires": [], "provides": ["x"]},
                    {"id": "b", "requires": ["y"], "provides": []},
                    {"id": "c", "requires": [], "provides": ["y"]},
                ],
                "workspaces": [{"name": "w", "part_ids": ["a", "b"]}],
            }
        )
    )
    s = summarize(doc)
    assert s["catalog"]["ok"] is True
    assert s["workspaces"][0]["ok"] is False
