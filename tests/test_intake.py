"""Tests for conversational intake (heuristics; LLM path mocked)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from intake import (
    _heuristic_intake,
    _normalize_llm_payload,
    _parse_intake_json,
    analyze_build_intake,
    merge_user_clarification,
)


def test_merge_user_clarification() -> None:
    assert merge_user_clarification("Build a PC", "") == "Build a PC"
    assert merge_user_clarification("", "budget 900") == "budget 900"
    m = merge_user_clarification("Gaming rig", "About $1200 total")
    assert "Gaming rig" in m and "1200" in m


@patch("intake._llm_intake", return_value=None)
def test_heuristic_sufficient_budget_and_gaming(_mock: object) -> None:
    out = analyze_build_intake("Build me a gaming PC for $1000")
    assert out["sufficient"] is True
    assert out["questions"] == []


@patch("intake._llm_intake", return_value=None)
def test_heuristic_sufficient_detailed_brief(_mock: object) -> None:
    long_brief = (
        "I need a workstation for Blender and some gaming on the side. "
        "Budget is $1800. I want 32GB RAM, quiet fans, no RGB, and a case that fits on a desk. "
        "I play 1440p and occasionally stream. I prefer NVIDIA for CUDA. "
        "I already have keyboard and mouse."
    )
    out = analyze_build_intake(long_brief)
    assert out["sufficient"] is True


@patch("intake._llm_intake", return_value=None)
def test_heuristic_insufficient_vague(_mock: object) -> None:
    out = analyze_build_intake("I want a computer")
    assert out["sufficient"] is False
    assert len(out["questions"]) >= 1


@patch("intake._llm_intake", return_value=None)
def test_heuristic_missing_budget_but_actionable_proceeds(_mock: object) -> None:
    out = analyze_build_intake("Build me a gaming PC with an RTX 4070")
    assert out["sufficient"] is True


@patch("intake._llm_intake", return_value=None)
def test_heuristic_lost_user_gets_exploration(_mock: object) -> None:
    out = analyze_build_intake("idk what to buy help")
    assert out["sufficient"] is False
    assert out.get("lost_user") is True
    assert len(out.get("exploration_prompts") or []) >= 1


def test_heuristic_direct_no_patch_short() -> None:
    """_heuristic_intake alone (no analyze wrapper) for empty string."""
    out = _heuristic_intake("")
    assert out["sufficient"] is False


def test_parse_intake_json_fenced() -> None:
    raw = '```json\n{"sufficient": true, "reason": "ok", "questions": [], "exploration_prompts": [], "lost_user": false}\n```'
    d = _parse_intake_json(raw)
    assert d is not None
    n = _normalize_llm_payload(d)
    assert n is not None
    assert n["sufficient"] is True


def test_normalize_llm_payload_rejects_missing_sufficient() -> None:
    assert _normalize_llm_payload({"reason": "x"}) is None


@patch("intake._llm_intake")
def test_analyze_prefers_llm_when_valid(mock_llm: object) -> None:
    mock_llm.return_value = {
        "sufficient": False,
        "reason": "LLM says so",
        "questions": ["Q1?"],
        "exploration_prompts": [],
        "lost_user": False,
    }
    out = analyze_build_intake("anything")
    assert out["reason"] == "LLM says so"
    assert out["questions"] == ["Q1?"]


@patch("intake._llm_intake")
def test_analyze_falls_back_when_llm_empty_questions(mock_llm: object) -> None:
    mock_llm.return_value = {
        "sufficient": False,
        "reason": "x",
        "questions": [],
        "exploration_prompts": [],
        "lost_user": False,
    }
    out = analyze_build_intake("computer")  # vague → heuristic fills questions
    assert not out["sufficient"]
    assert len(out["questions"]) >= 1
