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


def _smoke_model_id() -> str:
    """
    Model id for google.genai (AI Studio) — not always the same string as CrewAI/LiteLLM.

    Default `gemini-2.5-flash` (AI Studio); override with GESTALT_GEMINI_SMOKE_MODEL.
    """
    return os.environ.get("GESTALT_GEMINI_SMOKE_MODEL", "gemini-2.5-flash")


@pytest.mark.skipif(not _gemini_api_key(), reason="No GEMINI_API_KEY or GOOGLE_API_KEY (set in .env)")
def test_gemini_api_key_minimal_roundtrip() -> None:
    """Single generateContent call; fails fast if the key is invalid or model is wrong."""
    from google import genai
    from google.genai.errors import APIError

    key = _gemini_api_key()
    assert key

    client = genai.Client(api_key=key)
    model = _smoke_model_id()

    try:
        response = client.models.generate_content(
            model=model,
            contents='Reply with exactly one word: "pong"',
        )
    except APIError as e:
        # google.genai uses .code (HTTP status), not .status_code
        if getattr(e, "code", None) == 429:
            pytest.skip(
                "Gemini accepted the API key but returned 429 (quota/rate limit). "
                "Retry later or check https://ai.google.dev/gemini-api/docs/rate-limits"
            )
        raise

    text = (getattr(response, "text", None) or "").strip()
    assert text, "Empty response from Gemini — check model name and API enablement"
    assert len(text) < 500, "Unexpectedly long smoke reply"
