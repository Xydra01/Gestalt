"""Flask web UI for Gestalt PC Builder — crew-backed /build and streaming /build/stream."""

from __future__ import annotations

import json
import os
import queue
import threading
import time
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from dotenv import load_dotenv
from flask import Flask, Response, jsonify, render_template, request, stream_with_context

from crew import run_build_assistant
from eli5 import Eli5UnavailableError, generate_eli5_explanation
from http_utils import json_error, sse_comment, sse_pack
from intake import analyze_build_intake, merge_user_clarification
from price_comparison import enrich_crew_payload_with_pricing
from schemas import BuildRequest, ExplainRequest

_ROOT = Path(__file__).resolve().parent

_STARTED_AT = time.time()
_METRICS: dict[str, Any] = {
    "build_started": 0,
    "build_completed": 0,
    "build_errored": 0,
    "eli5_requested": 0,
    "eli5_errored": 0,
    "last_build_duration_ms": None,
}


def _inc(metric: str, by: int = 1) -> None:
    v = _METRICS.get(metric, 0)
    _METRICS[metric] = (int(v) if isinstance(v, int) else 0) + by


def _set(metric: str, value: Any) -> None:
    _METRICS[metric] = value


def _resolve_merged_prompt(body: dict) -> tuple[str, str]:
    """
    Return (merged_prompt, original_prompt_for_session).

    First turn: only ``prompt`` is set. Follow-up: ``original_prompt`` + ``clarification_answers``.
    """
    op = (body.get("original_prompt") or "").strip()
    p = (body.get("prompt") or "").strip()
    clar = (body.get("clarification_answers") or "").strip()
    if clar:
        base = op or p
        if not base:
            merged = clar
        else:
            merged = merge_user_clarification(base, clar)
        orig = op or p
        return merged, orig
    if p:
        return p, p
    return "", ""


def _safe_enrich_pricing(data: dict) -> dict:
    try:
        return enrich_crew_payload_with_pricing(data)
    except Exception:
        return data
load_dotenv(_ROOT / ".env")

app = Flask(
    __name__,
    template_folder=str(_ROOT / "templates"),
    static_folder=str(_ROOT / "static"),
)


@app.route("/")
def index() -> str:
    return render_template("index.html")


@app.route("/healthz")
def healthz():
    """
    Lightweight health endpoint for deploy checks and judge scans.

    Environment-driven metadata is optional:
    - GESTALT_VERSION: human-readable version tag (e.g. "0.1.0" or "hackathon-final")
    - GIT_SHA: git commit SHA when available in CI/CD
    """
    return jsonify(
        {
            "status": "ok",
            "service": "gestalt",
            "version": (os.environ.get("GESTALT_VERSION") or "").strip() or None,
            "commit": (os.environ.get("GIT_SHA") or "").strip() or None,
        }
    )


@app.route("/version")
def version():
    """Runtime metadata for debugging and deploy verification."""
    import platform
    import sys

    return jsonify(
        {
            "service": "gestalt",
            "version": (os.environ.get("GESTALT_VERSION") or "").strip() or None,
            "commit": (os.environ.get("GIT_SHA") or "").strip() or None,
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "uptime_s": round(time.time() - _STARTED_AT, 3),
        }
    )


@app.route("/metrics")
def metrics():
    """
    Minimal Prometheus-style metrics.

    This is intentionally lightweight and in-memory: it's meant as a judge/audit signal and
    basic production visibility, not a full monitoring stack.
    """
    lines: list[str] = []
    lines.append("# HELP gestalt_build_started Total build runs started.")
    lines.append("# TYPE gestalt_build_started counter")
    lines.append(f"gestalt_build_started {_METRICS.get('build_started', 0)}")
    lines.append("# HELP gestalt_build_completed Total build runs completed successfully.")
    lines.append("# TYPE gestalt_build_completed counter")
    lines.append(f"gestalt_build_completed {_METRICS.get('build_completed', 0)}")
    lines.append("# HELP gestalt_build_errored Total build runs that ended in error.")
    lines.append("# TYPE gestalt_build_errored counter")
    lines.append(f"gestalt_build_errored {_METRICS.get('build_errored', 0)}")
    lines.append("# HELP gestalt_eli5_requested Total ELI5 requests.")
    lines.append("# TYPE gestalt_eli5_requested counter")
    lines.append(f"gestalt_eli5_requested {_METRICS.get('eli5_requested', 0)}")
    lines.append("# HELP gestalt_eli5_errored Total ELI5 requests that errored.")
    lines.append("# TYPE gestalt_eli5_errored counter")
    lines.append(f"gestalt_eli5_errored {_METRICS.get('eli5_errored', 0)}")
    last = _METRICS.get("last_build_duration_ms")
    lines.append("# HELP gestalt_last_build_duration_ms Duration of the last completed build in milliseconds.")
    lines.append("# TYPE gestalt_last_build_duration_ms gauge")
    lines.append(f"gestalt_last_build_duration_ms {last if isinstance(last, (int, float)) else 'NaN'}")
    return Response("\n".join(lines) + "\n", mimetype="text/plain; version=0.0.4")

@app.route("/build", methods=["POST"])
def build():
    try:
        req = BuildRequest.model_validate(request.get_json(silent=True) or {})
    except ValidationError as e:
        return json_error("Invalid request", status=400, details=e.errors())
    body = req.model_dump()
    merged, original = _resolve_merged_prompt(body)
    if not merged.strip():
        return json_error("Missing or empty prompt", status=400)
    intake = analyze_build_intake(merged)
    if not intake.get("sufficient"):
        return jsonify(
            {
                "success": False,
                "needs_clarification": True,
                "intake": intake,
                "original_prompt": original,
                "merged_prompt": merged,
            }
        )
    _inc("build_started")
    started = time.time()
    try:
        raw = run_build_assistant(merged)
        data = json.loads(raw)
        data = _safe_enrich_pricing(data)
    except json.JSONDecodeError:
        _inc("build_errored")
        return json_error("Invalid crew response", status=500)
    except Exception as e:
        _inc("build_errored")
        return json_error(str(e), status=500)
    _inc("build_completed")
    _set("last_build_duration_ms", round((time.time() - started) * 1000))
    return jsonify(data)


@app.route("/build/stream", methods=["POST"])
def build_stream():
    try:
        req = BuildRequest.model_validate(request.get_json(silent=True) or {})
    except ValidationError as e:
        return json_error("Invalid request", status=400, details=e.errors())
    body = req.model_dump()
    merged, original = _resolve_merged_prompt(body)
    if not merged.strip():
        return json_error("Missing or empty prompt", status=400)

    def generate():
        """
        SSE generator for the UI.

        Emits spec-compliant SSE frames (``event:`` + ``data:``) so EventSource and intermediaries
        can handle the stream correctly. Also emits occasional keepalive comments to prevent idle
        timeouts on some proxies.
        """
        intake = analyze_build_intake(merged)
        if not intake.get("sufficient"):
            clarify = {
                "reason": intake.get("reason", ""),
                "questions": intake.get("questions") or [],
                "exploration_prompts": intake.get("exploration_prompts") or [],
                "lost_user": bool(intake.get("lost_user")),
                "original_prompt": original,
                "merged_prompt": merged,
            }
            yield sse_pack(event="clarify", data=clarify)
            yield sse_pack(
                event="complete",
                data={
                    "success": False,
                    "needs_clarification": True,
                    "intake": intake,
                    "original_prompt": original,
                },
            )
            return

        q: queue.Queue = queue.Queue()
        result: dict = {"payload": None, "err": None}
        _inc("build_started")
        started = time.time()

        def worker() -> None:
            try:
                raw = run_build_assistant(merged, stream_queue=q)
                data = json.loads(raw)
                result["payload"] = _safe_enrich_pricing(data)
            except json.JSONDecodeError as e:
                result["err"] = f"Invalid crew response: {e}"
            except Exception as e:
                result["err"] = str(e)

        t = threading.Thread(target=worker, daemon=True)
        t.start()
        # Keepalive so proxies/browsers don't think the connection stalled.
        idle_ticks = 0
        while t.is_alive() or not q.empty():
            try:
                item = q.get(timeout=0.2)
            except queue.Empty:
                idle_ticks += 1
                if idle_ticks >= 25:  # ~5s (25 * 0.2)
                    idle_ticks = 0
                    yield sse_comment("keepalive")
                continue
            idle_ticks = 0
            # Worker pushes items shaped like {"event": "...", ...}. Convert to proper SSE fields.
            if isinstance(item, dict):
                ev = item.get("event")
                if ev == "trace":
                    yield sse_pack(event="trace", data=item.get("entry"))
                    continue
                if ev == "clarify":
                    yield sse_pack(event="clarify", data=item.get("data"))
                    continue
                if ev == "complete":
                    yield sse_pack(event="complete", data=item.get("data"))
                    continue
                if ev == "error":
                    yield sse_pack(event="error", data={"message": item.get("message")})
                    continue
            # Fallback for unexpected shapes
            yield sse_pack(event="trace", data=item)
        t.join(timeout=600)
        if result["err"]:
            _inc("build_errored")
            yield sse_pack(event="error", data={"message": result["err"]})
        elif result["payload"] is not None:
            _inc("build_completed")
            _set("last_build_duration_ms", round((time.time() - started) * 1000))
            yield sse_pack(event="complete", data=result["payload"])
        else:
            _inc("build_errored")
            yield sse_pack(event="error", data={"message": "Build finished without a result."})

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.route("/explain", methods=["POST"])
def explain_eli5():
    """Beginner-friendly explanation for a completed build (requires Gemini API key)."""
    try:
        req = ExplainRequest.model_validate(request.get_json(silent=True) or {})
    except ValidationError as e:
        return json_error("Invalid request", status=400, details=e.errors())
    build = req.build
    analysis = req.analysis
    if not isinstance(build, dict) or not build:
        return json_error("Missing or empty build", status=400)
    if analysis is not None and not isinstance(analysis, dict):
        return json_error("analysis must be an object", status=400)
    _inc("eli5_requested")
    try:
        text = generate_eli5_explanation(build, analysis)
    except Eli5UnavailableError as e:
        _inc("eli5_errored")
        return json_error(str(e), status=503)
    except ValueError as e:
        _inc("eli5_errored")
        return json_error(str(e), status=400)
    except Exception as e:
        _inc("eli5_errored")
        return json_error(str(e), status=500)
    return jsonify({"eli5": text})


def main() -> None:
    """
    Local dev server. On Render (and similar), use gunicorn instead — see README.

    - ``PORT``: listen port (Render injects this).
    - ``HOST``: bind address (default ``0.0.0.0`` so the service accepts external traffic).
    - ``FLASK_DEBUG``: set to ``1``/``true`` to enable Flask debug (not for production).
    """
    port = int(os.environ.get("PORT", "5000"))
    host = os.environ.get("HOST", "127.0.0.1")
    debug = os.environ.get("FLASK_DEBUG", "").strip().lower() in ("1", "true", "yes")
    app.run(debug=debug, host=host, port=port)


if __name__ == "__main__":
    main()
