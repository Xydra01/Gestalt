"""Flask web UI for Gestalt PC Builder — mock /build until agents are wired."""

from __future__ import annotations

from pathlib import Path

from flask import Flask, jsonify, render_template
from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent
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
    # Mock data – later you'll replace with real agents
    mock_build = {
        "cpu": {"name": "AMD Ryzen 5 5600X", "price": 299},
        "gpu": {"name": "NVIDIA RTX 3060", "price": 329},
        "ram": {"name": "16GB DDR4 3200MHz", "price": 75},
        "storage": {"name": "1TB NVMe SSD", "price": 100},
        "motherboard": {"name": "B550 ATX", "price": 150},
        "psu": {"name": "650W 80+ Gold", "price": 90},
        "case": {"name": "Mid Tower", "price": 70},
    }
    total = sum(p["price"] for p in mock_build.values())
    savings = 150  # mock savings
    return jsonify(
        {
            "success": True,
            "build": mock_build,
            "total": total,
            "savings": savings,
            "analysis": "Mock analysis: This build is great for gaming.",
        }
    )


def main() -> None:
    app.run(debug=True, host="127.0.0.1", port=5000)


if __name__ == "__main__":
    main()
