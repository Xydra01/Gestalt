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
    extract_budget_from_prompt,
    infer_use_case_from_prompt,
    parse_analysis_result,
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
    """Full pipeline with API key set: kickoff mocked to return strict JSON."""

    class _Out:
        def __str__(self) -> str:
            return json.dumps(
                {
                    "budget": 1500,
                    "use_case": "creative work",
                    "priority": "max quality",
                    "constraints": [],
                }
            )

    mock_kickoff.return_value = _Out()
    with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-fake"}):
        out = json.loads(run_build_assistant("I want a $1500 editing rig"))
    assert out["status"] == "analysis_complete"
    assert out["analysis"]["budget"] == 1500
    assert out["allocation_category"] == "creative"
    assert out["allocation_rules"] == BUDGET_ALLOCATIONS["creative"]
    assert out["allocation_usd"]["gpu"] == pytest.approx(1500 * 0.25)
    assert "cpus" in out["parts_categories"]
    mock_kickoff.assert_called_once()


@patch("crew.Crew.kickoff")
def test_run_build_assistant_no_key_uses_heuristics(mock_kickoff: object) -> None:
    with patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
        out = json.loads(run_build_assistant("I want a $1500 editing rig"))
    mock_kickoff.assert_not_called()
    assert out["analysis"]["budget"] == 1500
    assert out["analysis"]["use_case"] == "creative work"
    assert out["allocation_category"] == "creative"
