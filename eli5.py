"""
Beginner-friendly (ELI5) explanations for a completed PC build — powered by Gemini when configured.

Feature map (master plan → code):
- Endpoint: `POST /explain` in `app.py` calls `generate_eli5_explanation`
- Trace-aware explanations: `_extract_trace_context` derives a compact context from `agent_trace`
- Degraded mode: raises `Eli5UnavailableError` when no `GEMINI_API_KEY`/`GOOGLE_API_KEY` is set
"""

from __future__ import annotations

import json
import os
from typing import Any

_BUILD_SLOTS = ("cpu", "gpu", "motherboard", "ram", "psu", "case")


class Eli5UnavailableError(Exception):
    """Raised when no LLM is configured for ELI5."""


def _strip_part_for_prompt(part: Any) -> dict[str, Any]:
    if not isinstance(part, dict):
        return {}
    out: dict[str, Any] = {}
    for k in ("id", "name", "title", "price", "socket", "ddr_gen", "ddr_support", "wattage", "tdp", "length_mm", "max_gpu_length_mm"):
        if k in part:
            out[k] = part[k]
    return out


def _sanitize_build_for_eli5(build: dict[str, Any]) -> dict[str, Any]:
    """Drop pricing-comparison blobs and keep human-relevant part fields."""
    out: dict[str, Any] = {}
    for slot in _BUILD_SLOTS:
        p = build.get(slot)
        if isinstance(p, dict):
            out[slot] = _strip_part_for_prompt(p)
    return out


_ELI5_PROMPT = """You are explaining a PC build to someone who has never built a computer.

You may receive trace context showing what the user asked for, how the system interpreted it,
what conflicts appeared during compatibility checks, and how they were resolved.

Use this context to explain the journey in plain English:
- What the user wanted.
- How the system interpreted that intent.
- Any compatibility issues caught and fixed automatically (if retries happened).
- Why the final validated build is the one being recommended.

If trace context is missing or partial, gracefully fall back to explaining only the final parts list.

PARTS JSON:
{parts_json}

ANALYSIS CONTEXT (may be empty):
{analysis_json}

TRACE CONTEXT (may be empty):
{trace_json}

Write a warm, encouraging explanation in plain English.

Requirements:
- For each major part category present (CPU, GPU, motherboard, RAM, PSU, case), use a clear heading line like:
  "🖥️ CPU — <product name>"
  then 2–4 short lines (plain English) covering:
  - What this part does, using a simple analogy (e.g. brain, artist, short-term memory).
  - Why this specific choice fits the user's stated needs (from analysis or from the parts).
- After all parts, add a section titled "How it all works together" with 2–4 sentences on how these parts cooperate.
- Avoid unexplained jargon (avoid acronyms without a quick gloss, or skip them).
- Use light emoji at section starts like the example (🖥️ 🎮 🧠 💾 🔌 📦).
- Separate sections with a blank line. Start with one title line:
  "📖 EXPLAIN LIKE I'M A BEGINNER"
  then a line of decorative dashes (e.g. ━━━━━━━━━━━━━━━) then the content.

Do not output JSON or markdown code fences — plain text only.
"""


def _extract_trace_context(
    build: dict[str, Any],
    analysis: dict[str, Any] | None,
    agent_trace: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Derive a compact explanation-focused context from ``agent_trace``."""
    trace = agent_trace if isinstance(agent_trace, list) else []
    user_request = ""
    analysis_from_trace: dict[str, Any] | None = None
    retry_entries: list[dict[str, Any]] = []
    validation_errors: list[dict[str, Any]] = []
    unresolved_text_errors: list[str] = []
    conflict_notes: list[str] = []

    for entry in trace:
        if not isinstance(entry, dict):
            continue
        kind = str(entry.get("kind") or "")
        if kind == "session_start" and not user_request:
            req = entry.get("user_input")
            if isinstance(req, str) and req.strip():
                user_request = req.strip()
        elif kind == "analysis_complete" and analysis_from_trace is None:
            parsed = entry.get("parsed_analysis")
            if isinstance(parsed, dict):
                analysis_from_trace = parsed
        elif kind == "retry_attempt":
            retry_entries.append(entry)
            prev_err = entry.get("prior_validation_error")
            if isinstance(prev_err, str) and prev_err.strip():
                unresolved_text_errors.append(prev_err.strip())
                conflict_notes.append(prev_err.strip())
        elif kind == "validation":
            errs = entry.get("errors")
            if isinstance(errs, list):
                for err in errs:
                    if isinstance(err, dict):
                        validation_errors.append(err)
                        fix = err.get("fix")
                        msg = err.get("message")
                        if isinstance(msg, str) and msg.strip() and isinstance(fix, str) and fix.strip():
                            conflict_notes.append(f"{msg.strip()} -> {fix.strip()}")
                        elif isinstance(fix, str) and fix.strip():
                            conflict_notes.append(fix.strip())

    typed_errors: list[str] = []
    for err in validation_errors:
        for key in ("code", "error_code", "type"):
            code = err.get(key)
            if isinstance(code, str) and code.strip():
                typed_errors.append(code.strip())
    for msg in unresolved_text_errors:
        for token in msg.replace(",", " ").split():
            if "_" in token and token.upper() == token and len(token) >= 4:
                typed_errors.append(token)

    retries_total = max(0, len(retry_entries) - 1)
    return {
        "user_request": user_request,
        "structured_intent": analysis_from_trace or (analysis if isinstance(analysis, dict) else {}),
        "attempt_count": len(retry_entries),
        "retry_count": retries_total,
        "typed_errors": sorted(set(typed_errors)),
        "conflicts_resolved": sorted(set(x for x in conflict_notes if x)),
        "final_validated_build": _sanitize_build_for_eli5(build),
    }


def generate_eli5_explanation(
    build: dict[str, Any],
    analysis: dict[str, Any] | None = None,
    agent_trace: list[dict[str, Any]] | None = None,
) -> str:
    """
    Call Gemini to produce the full ELI5 narrative, or raise :exc:`Eli5UnavailableError`.
    """
    key = (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or "").strip()
    if not key:
        raise Eli5UnavailableError("ELI5 requires GEMINI_API_KEY or GOOGLE_API_KEY in the environment.")

    slim = _sanitize_build_for_eli5(build)
    if not any(slim.get(s) for s in _BUILD_SLOTS):
        raise ValueError("Build has no recognizable parts to explain.")

    try:
        from google import genai
        from google.genai.errors import APIError
    except ImportError as e:
        raise Eli5UnavailableError("google-genai is required for ELI5.") from e

    model = (os.environ.get("GESTALT_ELI5_MODEL") or "").strip() or os.environ.get(
        "GESTALT_GEMINI_SMOKE_MODEL", "gemini-2.5-flash"
    )
    parts_json = json.dumps(slim, indent=2)
    analysis_json = json.dumps(analysis or {}, indent=2)
    trace_json = json.dumps(_extract_trace_context(build, analysis, agent_trace), indent=2)
    prompt = _ELI5_PROMPT.format(parts_json=parts_json, analysis_json=analysis_json, trace_json=trace_json)

    try:
        client = genai.Client(api_key=key)
        response = client.models.generate_content(model=model, contents=prompt)
    except APIError as e:
        raise RuntimeError(f"ELI5 generation failed: {e}") from e

    text = (getattr(response, "text", None) or "").strip()
    if not text:
        raise RuntimeError("ELI5 model returned empty text.")
    return text
