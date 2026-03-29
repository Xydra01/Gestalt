"""Flask web UI for Gestalt PC Builder — crew-backed /build and streaming /build/stream."""

from __future__ import annotations

import json
import queue
import threading
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, Response, jsonify, render_template, request, stream_with_context

from crew import run_build_assistant
from intake import analyze_build_intake, merge_user_clarification
from price_comparison import enrich_crew_payload_with_pricing

_ROOT = Path(__file__).resolve().parent


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


@app.route("/build", methods=["POST"])
def build():
    body = request.get_json(silent=True) or {}
    merged, original = _resolve_merged_prompt(body)
    if not merged.strip():
        return jsonify({"error": "Missing or empty prompt"}), 400
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
    try:
        raw = run_build_assistant(merged)
        data = json.loads(raw)
        data = _safe_enrich_pricing(data)
    except json.JSONDecodeError:
        return jsonify({"error": "Invalid crew response"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    return jsonify(data)


@app.route("/build/stream", methods=["POST"])
def build_stream():
    body = request.get_json(silent=True) or {}
    merged, original = _resolve_merged_prompt(body)
    if not merged.strip():
        return jsonify({"error": "Missing or empty prompt"}), 400

    def generate():
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
            yield "data: " + json.dumps({"event": "clarify", "data": clarify}, default=str) + "\n\n"
            yield (
                "data: "
                + json.dumps(
                    {
                        "event": "complete",
                        "data": {
                            "success": False,
                            "needs_clarification": True,
                            "intake": intake,
                            "original_prompt": original,
                        },
                    },
                    default=str,
                )
                + "\n\n"
            )
            return

        q: queue.Queue = queue.Queue()
        result: dict = {"payload": None, "err": None}

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
        while t.is_alive() or not q.empty():
            try:
                item = q.get(timeout=0.2)
            except queue.Empty:
                continue
            yield "data: " + json.dumps(item, default=str) + "\n\n"
        t.join(timeout=600)
        if result["err"]:
            yield "data: " + json.dumps({"event": "error", "message": result["err"]}, default=str) + "\n\n"
        elif result["payload"] is not None:
            yield (
                "data: "
                + json.dumps({"event": "complete", "data": result["payload"]}, default=str)
                + "\n\n"
            )
        else:
            yield (
                "data: "
                + json.dumps(
                    {"event": "error", "message": "Build finished without a result."},
                    default=str,
                )
                + "\n\n"
            )

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


def main() -> None:
    app.run(debug=True, host="127.0.0.1", port=5000)


if __name__ == "__main__":
    main()
