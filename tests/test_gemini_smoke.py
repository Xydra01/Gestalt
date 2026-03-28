"""
Optional integration test: one minimal call to the Gemini API to verify the key.

Skipped automatically when GEMINI_API_KEY / GOOGLE_API_KEY is unset (CI, fresh clones).

Run locally with a real key:
  uv run pytest tests/test_gemini_smoke.py -v

Or pass the key only for this command:
  GEMINI_API_KEY=... uv run pytest tests/test_gemini_smoke.py -v
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv


def _load_env() -> None:
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def _gemini_api_key() -> str | None:
    _load_env()
    k = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    return k.strip() if k else None


def _native_model_name() -> str:
    """
    google.genai uses model ids like 'gemini-1.5-flash' (no 'gemini/' LiteLLM prefix).
    """
    raw = os.environ.get("GESTALT_LLM_MODEL", "gemini/gemini-1.5-flash")
    if raw.startswith("gemini/"):
        return raw.split("/", 1)[1]
    return raw


@pytest.mark.skipif(not _gemini_api_key(), reason="No GEMINI_API_KEY or GOOGLE_API_KEY (set in .env)")
def test_gemini_api_key_minimal_roundtrip() -> None:
    """Single generateContent call; fails fast if the key is invalid or quota exceeded."""
    from google import genai

    key = _gemini_api_key()
    assert key

    client = genai.Client(api_key=key)
    model = os.environ.get("GESTALT_GEMINI_SMOKE_MODEL") or _native_model_name()

    response = client.models.generate_content(
        model=model,
        contents='Reply with exactly one word: "pong"',
    )

    text = (getattr(response, "text", None) or "").strip()
    assert text, "Empty response from Gemini — check model name and API enablement"
    assert len(text) < 500, "Unexpectedly long smoke reply"
