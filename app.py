"""Minimal Flask UI for parts catalog and compatibility results."""

from __future__ import annotations

from pathlib import Path

from flask import Flask, render_template
from dotenv import load_dotenv

from compatibility_checker import load_parts_document, summarize

_ROOT = Path(__file__).resolve().parent
load_dotenv(_ROOT / ".env")

app = Flask(
    __name__,
    template_folder=str(_ROOT / "templates"),
    static_folder=str(_ROOT / "static"),
)


@app.route("/")
def index() -> str:
    doc = load_parts_document(_ROOT / "parts.json")
    summary_data = summarize(doc)
    return render_template("index.html", summary=summary_data, parts=doc.get("parts", []))


def main() -> None:
    app.run(debug=True, host="127.0.0.1", port=5000)


if __name__ == "__main__":
    main()
