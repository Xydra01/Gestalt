"""Tests for ELI5 beginner explanations (mocked Gemini)."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from eli5 import (
    Eli5UnavailableError,
    _sanitize_build_for_eli5,
    generate_eli5_explanation,
)


def test_sanitize_strips_price_comparison() -> None:
    b = {
        "cpu": {"name": "AMD X", "price": 200, "price_comparison": {"amazon": {"price": 199}}},
        "gpu": {"name": "RTX", "price": 400},
    }
    s = _sanitize_build_for_eli5(b)
    assert "price_comparison" not in str(s)
    assert s["cpu"]["name"] == "AMD X"


def test_generate_raises_without_api_key() -> None:
    with patch.dict(os.environ, {"GEMINI_API_KEY": "", "GOOGLE_API_KEY": ""}):
        with pytest.raises(Eli5UnavailableError):
            generate_eli5_explanation({"cpu": {"name": "x"}}, None)


def test_generate_raises_empty_build() -> None:
    with patch.dict(os.environ, {"GEMINI_API_KEY": "fake-key"}):
        with pytest.raises(ValueError, match="recognizable parts"):
            generate_eli5_explanation({}, None)


@patch("google.genai.Client")
def test_generate_calls_gemini(mock_client_cls: MagicMock) -> None:
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    resp = MagicMock()
    resp.text = "📖 ELI5\n━━━━━━━━\nCPU line"
    mock_client.models.generate_content.return_value = resp

    with patch.dict(os.environ, {"GEMINI_API_KEY": "fake-key"}):
        out = generate_eli5_explanation(
            {
                "cpu": {"name": "Test CPU", "price": 100},
                "gpu": {"name": "Test GPU", "price": 200},
                "motherboard": {},
                "ram": {},
                "psu": {},
                "case": {},
            },
            {"budget": 1000, "use_case": "gaming"},
        )

    assert "CPU line" in out or "ELI5" in out
    mock_client.models.generate_content.assert_called_once()


def test_explain_route_ok() -> None:
    from app import app as flask_app

    with flask_app.test_client() as c:
        with patch("app.generate_eli5_explanation", return_value="Plain text ELI5"):
            rv = c.post(
                "/explain",
                json={
                    "build": {"cpu": {"name": "A"}},
                    "analysis": {"budget": 500},
                },
            )
    assert rv.status_code == 200
    data = rv.get_json()
    assert data["eli5"] == "Plain text ELI5"


def test_explain_route_missing_build() -> None:
    from app import app as flask_app

    with flask_app.test_client() as c:
        rv = c.post("/explain", json={})
    assert rv.status_code == 400
