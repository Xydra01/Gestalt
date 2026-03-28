"""Gestalt PC build crew — analysis task, budget allocation, mock validation."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from crewai import Crew, Process, Task
from dotenv import load_dotenv

from agents import analysis_agent, recommendation_agent, resolve_llm

_ROOT = Path(__file__).resolve().parent
load_dotenv(_ROOT / ".env")

# --- Fallback when the LLM returns prose or invalid JSON ----------------------------

DEFAULT_ANALYSIS: dict[str, Any] = {
    "budget": 1000,
    "use_case": "general productivity",
    "priority": "balanced",
    "constraints": [],
}

# Project plan percentages (gaming / creative / general)
BUDGET_ALLOCATIONS: dict[str, dict[str, float]] = {
    "gaming": {
        "gpu": 0.40,
        "cpu": 0.20,
        "mobo": 0.15,
        "ram": 0.10,
        "psu": 0.10,
        "case": 0.05,
    },
    "creative": {
        "gpu": 0.25,
        "cpu": 0.30,
        "mobo": 0.15,
        "ram": 0.15,
        "psu": 0.10,
        "case": 0.05,
    },
    "general": {
        "gpu": 0.15,
        "cpu": 0.35,
        "mobo": 0.20,
        "ram": 0.15,
        "psu": 0.10,
        "case": 0.05,
    },
}


def _parse_json_object_from_llm_text(text: str) -> dict[str, Any] | None:
    """Best-effort JSON object extraction from raw LLM output."""
    if not text or not str(text).strip():
        return None
    t = str(text).strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", t, re.IGNORECASE)
    if fence:
        t = fence.group(1).strip()
    try:
        data = json.loads(t)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        pass
    start = t.find("{")
    end = t.rfind("}")
    if start != -1 and end > start:
        try:
            data = json.loads(t[start : end + 1])
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def parse_analysis_result(raw: str) -> dict[str, Any]:
    """Parse crew kickoff output into an analysis dict; fall back to DEFAULT_ANALYSIS."""
    data = _parse_json_object_from_llm_text(raw)
    if not data:
        return {**DEFAULT_ANALYSIS}
    out = {**DEFAULT_ANALYSIS}
    b = data.get("budget")
    if isinstance(b, (int, float)) and b > 0:
        out["budget"] = int(round(float(b)))
    if isinstance(data.get("use_case"), str) and data["use_case"].strip():
        out["use_case"] = data["use_case"].strip()
    if isinstance(data.get("priority"), str) and data["priority"].strip():
        out["priority"] = data["priority"].strip()
    c = data.get("constraints")
    if isinstance(c, list):
        out["constraints"] = [str(x) for x in c if str(x).strip()]
    elif isinstance(c, str) and c.strip():
        out["constraints"] = [c.strip()]
    return out


def resolve_allocation_category(use_case: str) -> str:
    """Map free-text use_case to gaming | creative | general."""
    s = use_case.lower()
    # "game" alone is not a substring of "gaming"; match whole-word / explicit forms
    if re.search(r"\b(gaming|game)\b", s):
        return "gaming"
    if any(
        k in s
        for k in (
            "creative",
            "edit",
            "video",
            "photo",
            "render",
            "production",
            "stream",
            "3d",
        )
    ):
        return "creative"
    return "general"


def budget_rules_for_analysis(analysis: dict[str, Any]) -> tuple[str, dict[str, float], dict[str, float]]:
    """Return (category_key, percentage_rules, usd_per_category)."""
    category = resolve_allocation_category(str(analysis.get("use_case", "")))
    pct = BUDGET_ALLOCATIONS[category]
    budget = int(analysis.get("budget") or DEFAULT_ANALYSIS["budget"])
    usd = {k: round(budget * v, 2) for k, v in pct.items()}
    return category, pct, usd


def extract_budget_from_prompt(text: str) -> int | None:
    """Heuristic: pull a dollar amount from natural language (e.g. $1500)."""
    if not text:
        return None
    m = re.search(r"\$\s*([\d]{1,3}(?:,\d{3})+|\d+)", text)
    if not m:
        return None
    digits = m.group(1).replace(",", "")
    try:
        n = int(digits)
        return n if n > 0 else None
    except ValueError:
        return None


def infer_use_case_from_prompt(text: str) -> str | None:
    """When no LLM is available, infer use_case from keywords (hackathon fallback)."""
    t = text.lower()
    if any(
        k in t
        for k in (
            "edit",
            "editing",
            "video",
            "photo",
            "render",
            "creative",
            "stream",
            "davinci",
            "premiere",
            "after effects",
        )
    ):
        return "creative work"
    if re.search(r"\b(gaming|game)\b", t):
        return "gaming"
    return None


# --- Parts catalog -------------------------------------------------------------------


def load_parts() -> dict[str, Any]:
    """Load PC parts from parts.json; fall back to a tiny mock if missing."""
    path = _ROOT / "parts.json"
    if path.is_file():
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    return {
        "cpus": [{"id": "c1", "price": 200, "socket": "AM5", "tdp": 105}],
        "gpus": [{"id": "g1", "price": 400, "tdp": 200, "length_mm": 300}],
        "motherboards": [{"id": "m1", "price": 150, "socket": "AM5", "ddr_support": "DDR5"}],
        "ram": [{"id": "r1", "price": 80, "ddr_gen": "DDR5"}],
        "psus": [{"id": "p1", "price": 100, "wattage": 750}],
        "cases": [{"id": "case1", "price": 90, "max_gpu_length_mm": 350}],
    }


def validate_build(build: dict[str, Any]) -> dict[str, Any]:
    """Mock validator until compatibility_checker.validate_build is wired."""
    _ = build
    return {"passed": True, "errors": []}


# -------------------------------------------------------------------------------------


def run_build_assistant(user_input: str) -> str:
    """
    Run analysis crew on user_input, parse JSON, apply budget allocation rules.

    Returns a JSON string with analysis, allocation category, rule percentages, and USD splits.
    """
    parts_data = load_parts()
    _ = json.dumps(parts_data)  # reserved for recommendation / validation tasks

    raw_output = ""
    llm_ready = resolve_llm() is not None
    if llm_ready:
        analyst = analysis_agent()
        analysis_task = Task(
            description=(
                f"User request:\n{user_input}\n\n"
                "Your output must be ONLY a single valid JSON object with exactly these keys:\n"
                '  "budget" — number, total budget in USD (integer or float)\n'
                '  "use_case" — string, one of: gaming, creative work, general productivity, development\n'
                '  "priority" — string: max fps, max quality, or balanced\n'
                '  "constraints" — array of strings (use [] if none)\n'
                "Do not wrap in markdown. Do not add commentary. JSON only."
            ),
            expected_output=(
                '{"budget": <number>, "use_case": "<string>", "priority": "<string>", '
                '"constraints": [<strings>]}'
            ),
            agent=analyst,
        )

        crew = Crew(
            agents=[analyst],
            tasks=[analysis_task],
            process=Process.sequential,
            verbose=True,
        )
        try:
            raw_output = str(crew.kickoff())
        except Exception as e:
            raw_output = json.dumps({"_crew_error": str(e)})

    try:
        analysis = parse_analysis_result(raw_output)
    except (json.JSONDecodeError, TypeError, KeyError):
        analysis = {**DEFAULT_ANALYSIS}

    hinted = extract_budget_from_prompt(user_input)
    if hinted is not None:
        analysis["budget"] = hinted

    if not llm_ready:
        inferred_uc = infer_use_case_from_prompt(user_input)
        if inferred_uc:
            analysis["use_case"] = inferred_uc

    category, rules_pct, rules_usd = budget_rules_for_analysis(analysis)

    payload = {
        "status": "analysis_complete",
        "analysis": analysis,
        "allocation_category": category,
        "allocation_rules": rules_pct,
        "allocation_usd": rules_usd,
        "parts_categories": {k: len(v) if isinstance(v, list) else 0 for k, v in parts_data.items()},
    }
    if os.environ.get("GESTALT_DEBUG"):
        payload["raw_llm_output"] = raw_output[:4000]

    out = json.dumps(payload, indent=2)
    print(out)
    return out


def build_crew(topic: str = "parts compatibility") -> Crew:
    """Minimal two-task crew for LLM smoke tests (analysis + recommendation placeholders)."""
    a = analysis_agent()
    r = recommendation_agent()
    t1 = Task(
        description=f"Topic context: {topic}. Summarize as JSON placeholder.",
        expected_output="Short JSON string",
        agent=a,
    )
    t2 = Task(
        description="Using prior context, output OK.",
        expected_output="OK",
        agent=r,
        context=[t1],
    )
    return Crew(agents=[a, r], tasks=[t1, t2], process=Process.sequential, verbose=True)


def run_crew(topic: str = "parts compatibility") -> str:
    crew = build_crew(topic=topic)
    return str(crew.kickoff())


if __name__ == "__main__":
    run_build_assistant("I want a $1500 editing rig")
