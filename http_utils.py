from __future__ import annotations

import json
from typing import Any

from flask import Response, jsonify


def sse_pack(*, event: str | None = None, data: object | None = None) -> str:
    """
    Pack a single Server-Sent Event message.

    Uses SSE fields (event/data) rather than embedding the event name inside JSON.
    """
    lines: list[str] = []
    if event:
        lines.append(f"event: {event}")
    if data is not None:
        payload = json.dumps(data, default=str)
        # SSE allows multi-line data by repeating data: lines.
        for chunk in payload.splitlines() or [""]:
            lines.append(f"data: {chunk}")
    return "\n".join(lines) + "\n\n"


def sse_comment(text: str = "ping") -> str:
    """SSE keepalive comment line (ignored by EventSource)."""
    return f": {text}\n\n"


def json_error(message: str, *, status: int = 400, details: Any | None = None) -> tuple[Response, int]:
    payload: dict[str, Any] = {"error": message}
    if details is not None:
        payload["details"] = details
    return jsonify(payload), status

