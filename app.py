"""Flask web UI for Gestalt PC Builder — crew-backed /build and streaming /build/stream."""

from __future__ import annotations

import json
import queue
import threading
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, Response, jsonify, render_template, request, stream_with_context

from crew import run_build_assistant
from price_comparison import enrich_crew_payload_with_pricing

_ROOT = Path(__file__).resolve().parent


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
    prompt = (body.get("prompt") or "").strip()
    if not prompt:
        return jsonify({"error": "Missing or empty prompt"}), 400
    try:
        raw = run_build_assistant(prompt)
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
    prompt = (body.get("prompt") or "").strip()
    if not prompt:
        return jsonify({"error": "Missing or empty prompt"}), 400

    def generate():
        q: queue.Queue = queue.Queue()
        result: dict = {"payload": None, "err": None}

        def worker() -> None:
            try:
                raw = run_build_assistant(prompt, stream_queue=q)
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
