"""
End-to-end pipeline tests: Flask routes + SSE + mocked crew/ELI5 (no live LLM, no retailer APIs).

These exercises the same HTTP surface the UI uses:
``GET /``, ``POST /build``, ``POST /build/stream``, ``POST /explain``.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from app import app as flask_app
from crew import build_dict_from_selected_ids, total_price_for_build
from parts_catalog import load_parts_catalog


def _parse_sse_events(raw: bytes) -> list[dict]:
    """Parse ``text/event-stream`` body into JSON objects from ``data:`` lines."""
    out: list[dict] = []
    text = raw.decode("utf-8", errors="replace")
    for block in text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        for line in block.split("\n"):
            line = line.strip()
            if line.startswith("data: "):
                try:
                    out.append(json.loads(line[6:]))
                except json.JSONDecodeError:
                    pass
    return out


def _sample_success_crew_json() -> str:
    """Deterministic successful crew payload using the bundled parts catalog."""
    parts_data, src = load_parts_catalog()
    selected_ids = {
        "cpu": "amd-ryzen-5-7600",
        "gpu": "nvidia-rtx-4060",
        "motherboard": "gigabyte-b650m-ds3h",
        "ram": "corsair-vengeance-32gb",
        "psu": "corsair-cx650m",
        "case": "deepcool-cc560",
    }
    build = build_dict_from_selected_ids(selected_ids, parts_data)
    total = total_price_for_build(build)
    analysis = {
        "budget": 1500,
        "use_case": "gaming",
        "priority": "balanced",
        "constraints": [],
    }
    payload = {
        "success": True,
        "build": build,
        "total": total,
        "savings": round(total * 0.35, 2),
        "analysis": analysis,
        "agent_trace": [
            {"kind": "session_start", "user_input": "e2e", "parts_catalog_source": src},
            {"kind": "validation", "attempt": 1, "passed": True, "errors": []},
        ],
        "parts_catalog_source": src,
    }
    return json.dumps(payload)


@pytest.mark.e2e
def test_e2e_get_index() -> None:
    with flask_app.test_client() as c:
        rv = c.get("/")
    assert rv.status_code == 200
    assert b"GESTALT" in rv.data or b"Gestalt" in rv.data


@pytest.mark.e2e
@patch("intake._llm_intake", return_value=None)
@patch("app.run_build_assistant")
@patch("app._safe_enrich_pricing", side_effect=lambda d: d)
def test_e2e_build_stream_complete_pipeline(
    _mock_enrich: object,
    mock_run: object,
    _llm: object,
) -> None:
    """POST /build/stream with a sufficient prompt → SSE ends with ``complete`` + build."""
    mock_run.return_value = _sample_success_crew_json()

    with flask_app.test_client() as c:
        rv = c.post(
            "/build/stream",
            json={"prompt": "Build me a gaming PC for $1000"},
            content_type="application/json",
        )
    assert rv.status_code == 200
    assert "text/event-stream" in (rv.headers.get("Content-Type") or "")
    events = _parse_sse_events(rv.data)
    assert events, "expected at least one SSE data event"
    complete = [e for e in events if e.get("event") == "complete"]
    assert len(complete) == 1
    data = complete[0].get("data") or {}
    assert data.get("success") is True
    assert "cpu" in data.get("build", {})
    mock_run.assert_called_once()


@pytest.mark.e2e
@patch("intake._llm_intake", return_value=None)
def test_e2e_build_stream_clarify_path(_llm: object) -> None:
    """Vague prompt → ``clarify`` event and ``complete`` with ``needs_clarification`` (no crew)."""
    with flask_app.test_client() as c:
        rv = c.post(
            "/build/stream",
            json={"prompt": "I want a computer"},
            content_type="application/json",
        )
    assert rv.status_code == 200
    events = _parse_sse_events(rv.data)
    kinds = {e.get("event") for e in events}
    assert "clarify" in kinds
    complete = [e for e in events if e.get("event") == "complete"][0]
    inner = complete.get("data") or {}
    assert inner.get("needs_clarification") is True
    assert inner.get("success") is False


@pytest.mark.e2e
@patch("intake._llm_intake", return_value=None)
@patch("app.run_build_assistant")
@patch("app._safe_enrich_pricing", side_effect=lambda d: d)
def test_e2e_build_json_route(_mock_enrich: object, mock_run: object, _llm: object) -> None:
    """POST /build returns JSON body (non-streaming path)."""
    mock_run.return_value = _sample_success_crew_json()

    with flask_app.test_client() as c:
        rv = c.post(
            "/build",
            json={"prompt": "Build me a gaming PC for $1000"},
            content_type="application/json",
        )
    assert rv.status_code == 200
    data = rv.get_json()
    assert data.get("success") is True
    assert "build" in data


@pytest.mark.e2e
@patch("app.generate_eli5_explanation", return_value="Plain-English block.")
def test_e2e_explain_route(mock_eli5: object) -> None:
    """POST /explain with a minimal build → ``eli5`` string."""
    with flask_app.test_client() as c:
        rv = c.post(
            "/explain",
            json={"build": {"cpu": {"name": "Test CPU", "price": 100}}, "analysis": {"budget": 900}},
            content_type="application/json",
        )
    assert rv.status_code == 200
    data = rv.get_json()
    assert data.get("eli5") == "Plain-English block."
    mock_eli5.assert_called_once()


@pytest.mark.e2e
def test_e2e_explain_missing_build_400() -> None:
    with flask_app.test_client() as c:
        rv = c.post("/explain", json={}, content_type="application/json")
    assert rv.status_code == 400
