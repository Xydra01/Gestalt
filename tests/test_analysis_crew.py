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
    total_price_for_build,
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
                "ram": "corsair-vengeance-32gb",
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
    assert out["success"] is True
    assert out["analysis"]["budget"] == 1500
    assert out["build"]["cpu"]["id"] == "amd-ryzen-5-7600"
    assert out["build"]["ram"]["id"] == "corsair-vengeance-32gb"
    total = out["total"]
    assert total == total_price_for_build(out["build"])
    assert out["savings"] == pytest.approx(round(total * 0.35, 2))
    trace = out["agent_trace"]
    assert any(e.get("kind") == "validation" and e.get("passed") for e in trace)
    assert mock_kickoff.call_count == 2


@patch("crew.Crew.kickoff")
def test_run_build_assistant_no_key_uses_heuristics(mock_kickoff: object) -> None:
    with patch.dict(
        os.environ,
        {"GEMINI_API_KEY": "", "GOOGLE_API_KEY": "", "OPENAI_API_KEY": ""},
    ):
        out = json.loads(run_build_assistant("I want a $1500 editing rig"))
    mock_kickoff.assert_not_called()
    assert out["success"] is True
    assert out["analysis"]["budget"] == 1500
    assert out["analysis"]["use_case"] == "creative work"
    assert out["build"]["cpu"].get("id") == "intel-core-i3-14100"
    assert out["total"] == total_price_for_build(out["build"])
    assert "agent_trace" in out
    assert any(x.get("kind") == "recommendation_skipped" for x in out["agent_trace"])


@patch("crew.validate_build")
@patch("crew.Crew.kickoff")
def test_retry_loop_exhausted(mock_kickoff: object, mock_validate: object) -> None:
    analysis_json = json.dumps(
        {"budget": 1000, "use_case": "gaming", "priority": "balanced", "constraints": []}
    )
    rec = json.dumps(
        {
            "selected_ids": {
                "cpu": "amd-ryzen-5-7600",
                "gpu": "nvidia-rtx-4060",
                "motherboard": "gigabyte-b650m-ds3h",
                "ram": "corsair-vengeance-32gb",
                "psu": "corsair-cx650m",
                "case": "deepcool-cc560",
            }
        }
    )
    mock_kickoff.side_effect = [analysis_json, rec, rec, rec]
    mock_validate.return_value = {
        "passed": False,
        "errors": [{"code": "TEST", "part": "gpu", "message": "x", "fix": "pick another gpu"}],
    }
    with patch.dict(os.environ, {"GEMINI_API_KEY": "fake"}):
        out = json.loads(run_build_assistant("gaming pc $1000"))
    assert out["success"] is False
    assert "3 attempts" in out["error"]
    assert mock_kickoff.call_count == 4
    assert mock_validate.call_count == 3
    assert len(out["agent_trace"]) >= 3


@patch("crew.validate_build")
@patch("crew.Crew.kickoff")
def test_retry_loop_succeeds_on_second_attempt(mock_kickoff: object, mock_validate: object) -> None:
    mock_kickoff.side_effect = [
        json.dumps({"budget": 1200, "use_case": "gaming", "priority": "balanced", "constraints": []}),
        json.dumps(
            {
                "selected_ids": {
                    "cpu": "amd-ryzen-5-7600",
                    "gpu": "nvidia-rtx-4060",
                    "motherboard": "gigabyte-b650m-ds3h",
                    "ram": "corsair-vengeance-32gb",
                    "psu": "corsair-cx650m",
                    "case": "deepcool-cc560",
                }
            }
        ),
        json.dumps(
            {
                "selected_ids": {
                    "cpu": "amd-ryzen-5-7600",
                    "gpu": "nvidia-rtx-4060",
                    "motherboard": "gigabyte-b650m-ds3h",
                    "ram": "corsair-vengeance-32gb",
                    "psu": "corsair-cx650m",
                    "case": "deepcool-cc560",
                }
            }
        ),
    ]
    mock_validate.side_effect = [
        {"passed": False, "errors": [{"fix": "adjust parts"}]},
        {"passed": True, "errors": []},
    ]
    with patch.dict(os.environ, {"GEMINI_API_KEY": "fake"}):
        out = json.loads(run_build_assistant("gaming pc"))
    assert out["success"] is True
    assert mock_kickoff.call_count == 3
    assert mock_validate.call_count == 2


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


def test_draft_recommendation_prompt_includes_previous_validation_error() -> None:
    analysis = {"budget": 400, "use_case": "gaming", "priority": "balanced", "constraints": []}
    cat, pct, usd = budget_rules_for_analysis(analysis)
    parts = {"cpus": [{"id": "x", "price": 100}]}
    text = draft_recommendation_prompt(
        analysis, "Use a shorter GPU.", cat, pct, usd, parts
    )
    assert "Previous validation error: Use a shorter GPU." in text


def test_trace_task_completed_serializes_task_output() -> None:
    from crewai.tasks.output_format import OutputFormat
    from crewai.tasks.task_output import TaskOutput

    import crew as crew_mod

    buf: list[dict] = []
    out = TaskOutput(
        description="Do a thing",
        raw='{"a": 1}',
        agent="test-agent",
        output_format=OutputFormat.RAW,
    )
    crew_mod._trace_task_completed(buf, "unit_test", out)
    assert len(buf) == 1
    assert buf[0]["kind"] == "llm_task_output"
    assert buf[0]["crew_phase"] == "unit_test"
    assert buf[0]["raw"] == '{"a": 1}'
    assert buf[0]["agent"] == "test-agent"
