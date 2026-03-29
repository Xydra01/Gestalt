"""
Pre-build intake: decide if the user prompt is specific enough to run the crew, or ask for clarification.

Uses Gemini when an API key is available; otherwise heuristics based on :mod:`crew` helpers.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

from crew import extract_budget_from_prompt, infer_use_case_from_prompt


def merge_user_clarification(original: str, answers: str) -> str:
    """Combine the first message with follow-up answers for a single build prompt."""
    o = (original or "").strip()
    a = (answers or "").strip()
    if not a:
        return o
    if not o:
        return a
    return f"{o}\n\nAdditional details from you:\n{a}"


_LOST_PHRASES = (
    "no idea",
    "don't know",
    "dont know",
    "not sure",
    "idk",
    "help me choose",
    "help me pick",
    "what should i",
    "suggest a",
    "recommend",
)


def _looks_lost_user(text: str) -> bool:
    t = text.lower().strip()
    if len(t) < 12:
        return True
    return any(p in t for p in _LOST_PHRASES)


def _has_dev_or_productivity(text: str) -> bool:
    t = text.lower()
    return bool(
        re.search(
            r"\b(dev|developer|coding|programming|software|work from home|office|school|student|productivity)\b",
            t,
        )
    )


def _heuristic_intake(user_input: str) -> dict[str, Any]:
    """
    Fast path without LLM. Sets ``sufficient`` when budget + use-case signals exist,
    or the prompt is long and informative enough.
    """
    raw = (user_input or "").strip()
    if not raw:
        return {
            "sufficient": False,
            "reason": "Empty request.",
            "questions": ["What budget (USD) are you aiming for, and what will you use the PC for most?"],
            "exploration_prompts": [
                "Is this mainly for games, work/school, or creative apps (video/photo)?",
                "Rough budget: under $800, $800–$1500, or over $1500?",
            ],
            "lost_user": True,
        }

    budget = extract_budget_from_prompt(raw)
    use_guess = infer_use_case_from_prompt(raw)
    has_use = use_guess is not None or _has_dev_or_productivity(raw)
    lost = _looks_lost_user(raw)
    n = len(raw)
    # Signals that the user is asking for a *specific* build even if they forgot a budget.
    # This prevents a "clarify forever" softlock: we can proceed using a sensible default budget.
    part_intent = bool(
        re.search(
            r"\b(rtx|radeon|ryzen|intel|core i[3579]|am4|am5|lga\s?1700|ddr4|ddr5|nvme|itx|matx|atx)\b",
            raw.lower(),
        )
    )

    # Detailed build brief: proceed without forcing more Q&A
    if n >= 140 and budget is not None and has_use:
        return {
            "sufficient": True,
            "reason": "Detailed request with budget and use-case signals.",
            "questions": [],
            "exploration_prompts": [],
            "lost_user": False,
        }

    if budget is not None and has_use:
        return {
            "sufficient": True,
            "reason": "Budget and primary use case are stated.",
            "questions": [],
            "exploration_prompts": [],
            "lost_user": False,
        }

    # Missing budget, but the user intent is actionable (use-case + specificity).
    # We proceed and let the build pipeline assume a reasonable default budget.
    if budget is None and has_use and not lost and (n >= 28 or part_intent):
        return {
            "sufficient": True,
            "reason": "No budget was given — proceeding with a reasonable default budget assumption.",
            "questions": [],
            "exploration_prompts": [],
            "lost_user": False,
        }

    # High-level but actionable: e.g. "$1200 gaming PC" — budget + gaming in few words
    if budget is not None and n >= 18 and re.search(r"\b(gaming|game|gpu|fps|1440p|1080p|4k)\b", raw.lower()):
        return {
            "sufficient": True,
            "reason": "Budget given with clear gaming intent.",
            "questions": [],
            "exploration_prompts": [],
            "lost_user": False,
        }

    questions: list[str] = []
    exploration: list[str] = []

    if budget is None:
        questions.append("What is your target budget in USD for the whole PC (parts only)?")
    if not has_use:
        questions.append(
            "What is the main use: gaming, creative work (video/photo/3D), productivity/office, or software development?"
        )
    if len(questions) < 2 and n < 50:
        questions.append("Any hard constraints (size, noise, RGB off, specific brands)?")

    if lost or (budget is None and not has_use and n < 80):
        exploration.extend(
            [
                "Roughly: games, work/school, or content creation?",
                "Ballpark budget: under $800, $800–$1500, or over $1500?",
            ]
        )

    reason = "Need a clearer budget and/or primary use case before recommending parts."
    if lost:
        reason = "Request looks open-ended — a bit more direction will produce a better parts list."

    return {
        "sufficient": False,
        "reason": reason,
        "questions": questions[:3],
        "exploration_prompts": exploration[:3],
        "lost_user": lost,
    }


def _parse_intake_json(text: str) -> dict[str, Any] | None:
    t = (text or "").strip()
    if not t:
        return None
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


def _normalize_llm_payload(data: dict[str, Any]) -> dict[str, Any] | None:
    if "sufficient" not in data:
        return None
    suf = data.get("sufficient")
    if not isinstance(suf, bool):
        return None
    qs = data.get("questions")
    ex = data.get("exploration_prompts")
    if qs is not None and not isinstance(qs, list):
        return None
    if ex is not None and not isinstance(ex, list):
        return None
    questions = [str(x).strip() for x in (qs or []) if str(x).strip()][:3]
    exploration = [str(x).strip() for x in (ex or []) if str(x).strip()][:3]
    reason = data.get("reason")
    reason_s = str(reason).strip() if reason is not None else ""
    lost = bool(data.get("lost_user", False))
    return {
        "sufficient": suf,
        "reason": reason_s or ("Ready to build." if suf else "More detail needed."),
        "questions": questions,
        "exploration_prompts": exploration,
        "lost_user": lost,
    }


_INTAKE_LLM_PROMPT = """You triage a PC build request before any parts are chosen.

Decide if there is ENOUGH information to recommend parts (budget ballpark + primary use, OR a long detailed brief).

Rules:
- sufficient=true if: user gave a USD budget (or clear tier like "around $1000") AND primary use (gaming, work, creative, dev), OR the message is detailed (roughly 120+ words) with constraints.
- sufficient=true for short high-level asks like "$1000 gaming PC" or "1500 dollar video editing rig" — budget + use clear.
- sufficient=false if: missing budget, missing use case, or message is extremely vague ("help me with a PC", "best computer").
- If the user seems lost or unsure, set lost_user=true and add helpful exploration_prompts (short multiple-choice style questions).

Output ONLY valid JSON (no markdown) with keys:
{
  "sufficient": boolean,
  "reason": string (one sentence),
  "questions": string[] (max 3, specific follow-ups if sufficient is false),
  "exploration_prompts": string[] (max 3, only if lost_user or sufficient is false),
  "lost_user": boolean
}

User message:
"""


def _llm_intake(user_input: str) -> dict[str, Any] | None:
    key = (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or "").strip()
    if not key:
        return None
    try:
        from google import genai
        from google.genai.errors import APIError
    except ImportError:
        return None

    model = os.environ.get("GESTALT_INTAKE_MODEL") or os.environ.get(
        "GESTALT_GEMINI_SMOKE_MODEL", "gemini-2.5-flash"
    )
    try:
        client = genai.Client(api_key=key)
        response = client.models.generate_content(
            model=model,
            contents=_INTAKE_LLM_PROMPT + user_input.strip(),
        )
    except APIError:
        return None
    except Exception:
        return None

    text = (getattr(response, "text", None) or "").strip()
    parsed = _parse_intake_json(text)
    if not parsed:
        return None
    return _normalize_llm_payload(parsed)


def analyze_build_intake(user_input: str) -> dict[str, Any]:
    """
    Return intake decision with keys: sufficient, reason, questions, exploration_prompts, lost_user.

    Prefers LLM when configured; falls back to :func:`_heuristic_intake` on failure or no key.
    """
    raw = (user_input or "").strip()
    llm_out = _llm_intake(raw)
    if llm_out is not None:
        # Ensure at least one actionable question when insufficient
        if not llm_out["sufficient"]:
            if not llm_out["questions"] and not llm_out["exploration_prompts"]:
                return _heuristic_intake(raw)
        return llm_out
    return _heuristic_intake(raw)
