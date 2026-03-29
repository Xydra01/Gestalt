"""
Contract tests for the /build/stream SSE output format.

Goal: make the stream "judge obvious" and spec-compliant:
- uses `event:` and `data:` fields (not JSON with an embedded "event" key)
- `data:` is JSON for trace/clarify/complete/error events
- emits occasional keepalive comment frames (": keepalive") during idle
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from app import app as flask_app


def _split_sse(raw: bytes) -> list[str]:
    text = raw.decode("utf-8", errors="replace")
    return [b for b in (blk.strip() for blk in text.split("\n\n")) if b]


def _first_data_json(block: str) -> object | None:
    data_lines: list[str] = []
    for line in block.split("\n"):
        line = line.rstrip("\r")
        if line.startswith("data:"):
            data_lines.append(line.split(":", 1)[1].lstrip())
    if not data_lines:
        return None
    payload = "\n".join(data_lines).strip()
    return json.loads(payload) if payload else None


@pytest.mark.e2e
@patch("intake._llm_intake", return_value=None)
@patch("app.run_build_assistant")
@patch("app._safe_enrich_pricing", side_effect=lambda d: d)
def test_sse_uses_event_field_and_json_data(_mock_enrich: object, mock_run: object, _llm: object) -> None:
    mock_run.return_value = json.dumps(
        {
            "success": True,
            "build": {"cpu": {"id": "amd-ryzen-5-7600", "price": 200}},
            "total": 200,
            "savings": 0,
            "analysis": {"budget": 1000, "use_case": "gaming", "priority": "balanced", "constraints": []},
            "agent_trace": [],
            "parts_catalog_source": "embedded_mock",
        }
    )
    with flask_app.test_client() as c:
        rv = c.post("/build/stream", json={"prompt": "Build me a gaming PC for $1000"})
    assert rv.status_code == 200
    assert "text/event-stream" in (rv.headers.get("Content-Type") or "")

    blocks = _split_sse(rv.data)
    # We should see at least one "event:" line in the stream output.
    assert any("event:" in b for b in blocks)

    # And we should see an event: complete with JSON data payload.
    complete_blocks = [b for b in blocks if "event: complete" in b]
    assert complete_blocks, "expected an event: complete SSE frame"
    data = _first_data_json(complete_blocks[-1])
    assert isinstance(data, dict)
    assert data.get("success") is True


@pytest.mark.e2e
@patch("intake._llm_intake", return_value=None)
def test_sse_clarify_is_event_and_json(_llm: object) -> None:
    with flask_app.test_client() as c:
        rv = c.post("/build/stream", json={"prompt": "I want a computer"})
    assert rv.status_code == 200
    blocks = _split_sse(rv.data)
    clarify_blocks = [b for b in blocks if "event: clarify" in b]
    assert clarify_blocks, "expected an event: clarify SSE frame"
    payload = _first_data_json(clarify_blocks[0])
    assert isinstance(payload, dict)
    assert "questions" in payload


@pytest.mark.e2e
@patch("intake._llm_intake", return_value=None)
@patch("app.run_build_assistant")
def test_sse_keepalive_comment_frames(mock_run: object, _llm: object) -> None:
    """
    Keepalive comments are emitted when the worker is alive but the queue is empty.

    We simulate this by making run_build_assistant block briefly so the SSE generator loops with no queue items.
    """
    import time

    def slow_build(*_args, **_kwargs) -> str:
        time.sleep(6.0)
        return json.dumps(
            {
                "success": True,
                "build": {"cpu": {"id": "amd-ryzen-5-7600", "price": 200}},
                "total": 200,
                "savings": 0,
                "analysis": {"budget": 1000, "use_case": "gaming", "priority": "balanced", "constraints": []},
                "agent_trace": [],
                "parts_catalog_source": "embedded_mock",
            }
        )

    mock_run.side_effect = slow_build
    with flask_app.test_client() as c:
        rv = c.post("/build/stream", json={"prompt": "Build me a gaming PC for $1000"})
    assert rv.status_code == 200
    text = rv.data.decode("utf-8", errors="replace")
    assert ": keepalive" in text

