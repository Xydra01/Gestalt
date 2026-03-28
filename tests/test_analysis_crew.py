"""Unit tests for analysis parsing and budget allocation (no LLM)."""

from __future__ import annotations

import json
import os
from unittest.mock import patch

import pytest

from crew import (
    BUDGET_ALLOCATIONS,
    DEFAULT_ANALYSIS,
    budget_rules_for_analysis,
    build_dict_from_selected_ids,
    draft_recommendation_prompt,
    extract_budget_from_prompt,
    infer_use_case_from_prompt,
    parse_analysis_result,
    parse_selected_ids,
    resolve_allocation_category,
    run_build_assistant,
)


def test_parse_analysis_result_valid_json() -> None:
    raw = '{"budget": 1500, "use_case": "creative work", "priority": "max quality", "constraints": []}'
    d = parse_analysis_result(raw)
    assert d["budget"] == 1500
    assert d["use_case"] == "creative work"
    assert d["priority"] == "max quality"
    assert d["constraints"] == []


def test_parse_analysis_result_fenced() -> None:
    raw = 'Here:\n```json\n{"budget": 900, "use_case": "gaming", "priority": "balanced", "constraints": ["RGB"]}\n```'
    d = parse_analysis_result(raw)
    assert d["budget"] == 900
    assert d["use_case"].lower() == "gaming"


def test_parse_analysis_result_fallback_on_garbage() -> None:
    d = parse_analysis_result("not json at all")
    assert d == DEFAULT_ANALYSIS


def test_resolve_allocation_category() -> None:
    assert resolve_allocation_category("gaming") == "gaming"
    assert resolve_allocation_category("Video editing") == "creative"
    assert resolve_allocation_category("development") == "general"


def test_infer_use_case_from_prompt() -> None:
    assert infer_use_case_from_prompt("I want a $1500 editing rig") == "creative work"
    assert infer_use_case_from_prompt("pure gaming pc") == "gaming"


def test_budget_rules_for_analysis_editing_rig() -> None:
    analysis = {
        "budget": 1500,
        "use_case": "creative work for video editing",
        "priority": "max quality",
        "constraints": [],
    }
    cat, pct, usd = budget_rules_for_analysis(analysis)
    assert cat == "creative"
    assert pct == BUDGET_ALLOCATIONS["creative"]
    assert usd["gpu"] == round(1500 * 0.25, 2)
    assert abs(sum(usd.values()) - 1500) < 0.05


def test_extract_budget_from_prompt() -> None:
    assert extract_budget_from_prompt("I want a $1500 editing rig") == 1500
    assert extract_budget_from_prompt("budget $2,000 for the tower") == 2000
    assert extract_budget_from_prompt("no money here") is None


@patch("crew.Crew.kickoff")
def test_run_build_assistant_mocked_llm(mock_kickoff: object) -> None:
    """Analysis + recommendation crews: two kickoffs with JSON matching parts.json ids."""

    analysis_json = json.dumps(
        {
            "budget": 1500,
            "use_case": "creative work",
            "priority": "max quality",
            "constraints": [],
        }
    )
    recommendation_json = json.dumps(
        {
            "selected_ids": {
                "cpu": "amd-ryzen-5-7600",
                "gpu": "nvidia-rtx-4060",
                "motherboard": "gigabyte-b650m-ds3h",
                "ram": "corsair-vengeance-lpx-16gb",
                "psu": "corsair-cx650m",
                "case": "deepcool-cc560",
            }
        }
    )

    mock_kickoff.side_effect = [analysis_json, recommendation_json]
    with patch.dict(
        os.environ,
        {"GEMINI_API_KEY": "fake-gemini-key", "GOOGLE_API_KEY": "", "OPENAI_API_KEY": ""},
    ):
        out = json.loads(run_build_assistant("I want a $1500 editing rig"))
    assert out["status"] == "recommendation_complete"
    assert out["analysis"]["budget"] == 1500
    assert out["allocation_category"] == "creative"
    assert out["allocation_rules"] == BUDGET_ALLOCATIONS["creative"]
    assert out["allocation_usd"]["gpu"] == pytest.approx(1500 * 0.25)
    assert "cpus" in out["parts_categories"]
    assert out["build"]["cpu"]["id"] == "amd-ryzen-5-7600"
    assert out["build"]["gpu"]["id"] == "nvidia-rtx-4060"
    assert out["selected_ids"]["motherboard"] == "gigabyte-b650m-ds3h"
    assert mock_kickoff.call_count == 2


@patch("crew.Crew.kickoff")
def test_run_build_assistant_no_key_uses_heuristics(mock_kickoff: object) -> None:
    with patch.dict(
        os.environ,
        {"GEMINI_API_KEY": "", "GOOGLE_API_KEY": "", "OPENAI_API_KEY": ""},
    ):
        out = json.loads(run_build_assistant("I want a $1500 editing rig"))
    mock_kickoff.assert_not_called()
    assert out["status"] == "recommendation_complete"
    assert out["analysis"]["budget"] == 1500
    assert out["analysis"]["use_case"] == "creative work"
    assert out["allocation_category"] == "creative"
    assert out["selected_ids"] == {}
    assert out["build"]["cpu"].get("id") == "intel-core-i3-14100"


def test_parse_selected_ids_fenced() -> None:
    raw = """Here you go:
```json
{"selected_ids": {"cpu": "a", "gpu": "b", "motherboard": "m", "ram": "r", "psu": "p", "case": "c"}}
```"""
    d = parse_selected_ids(raw)
    assert d["cpu"] == "a"
    assert d["gpu"] == "b"


def test_build_dict_fallback_when_slot_missing() -> None:
    parts_data = {
        "cpus": [{"id": "c-first", "price": 1}],
        "gpus": [{"id": "g-first", "price": 2}],
        "motherboards": [{"id": "mb-first", "price": 3}],
        "ram": [{"id": "r-first", "price": 4}],
        "psus": [{"id": "p-first", "price": 5}],
        "cases": [{"id": "case-first", "price": 6}],
    }
    # LLM omits gpu -> first gpu
    b = build_dict_from_selected_ids({"cpu": "c-first"}, parts_data)
    assert b["cpu"]["id"] == "c-first"
    assert b["gpu"]["id"] == "g-first"


def test_draft_recommendation_prompt_contains_rules_and_catalog() -> None:
    analysis = {"budget": 500, "use_case": "gaming", "priority": "balanced", "constraints": []}
    cat, pct, usd = budget_rules_for_analysis(analysis)
    parts = {"cpus": [{"id": "x", "price": 100}]}
    text = draft_recommendation_prompt(analysis, "", cat, pct, usd, parts)
    assert "500" in text or "gaming" in text
    assert '"cpus"' in text or "cpus" in text
    assert "selected_ids" in text
