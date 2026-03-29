"""
Beginner-friendly (ELI5) explanations for a completed PC build — powered by Gemini when configured.
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

Here is the parts list (JSON). The user's analysis context (budget, goals) may be included below it.

PARTS JSON:
{parts_json}

ANALYSIS CONTEXT (may be empty):
{analysis_json}

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


def generate_eli5_explanation(
    build: dict[str, Any],
    analysis: dict[str, Any] | None = None,
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
    prompt = _ELI5_PROMPT.format(parts_json=parts_json, analysis_json=analysis_json)

    try:
        client = genai.Client(api_key=key)
        response = client.models.generate_content(model=model, contents=prompt)
    except APIError as e:
        raise RuntimeError(f"ELI5 generation failed: {e}") from e

    text = (getattr(response, "text", None) or "").strip()
    if not text:
        raise RuntimeError("ELI5 model returned empty text.")
    return text
