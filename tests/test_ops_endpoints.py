from __future__ import annotations

from unittest.mock import patch


def test_healthz_ok() -> None:
    from app import app as flask_app

    with flask_app.test_client() as c:
        rv = c.get("/healthz")
    assert rv.status_code == 200
    body = rv.get_json()
    assert body["status"] == "ok"
    assert body["service"] == "gestalt"


def test_version_ok() -> None:
    from app import app as flask_app

    with flask_app.test_client() as c:
        rv = c.get("/version")
    assert rv.status_code == 200
    body = rv.get_json()
    assert body["service"] == "gestalt"
    assert "python" in body
    assert "uptime_s" in body


def test_metrics_increments_on_build_and_explain() -> None:
    from app import app as flask_app

    with flask_app.test_client() as c:
        base = c.get("/metrics").get_data(as_text=True)
        assert "gestalt_build_started" in base

        with patch("app.run_build_assistant", return_value='{"success": true, "build": {}, "total": 0, "savings": 0, "analysis": {}, "agent_trace": [], "parts_catalog_source": "embedded_mock"}'):
            rv = c.post("/build", json={"prompt": "Build me a gaming PC for $1000"})
        assert rv.status_code == 200

        with patch("app.generate_eli5_explanation", return_value="ok"):
            rv2 = c.post("/explain", json={"build": {"cpu": {"name": "x"}}, "analysis": {}})
        assert rv2.status_code == 200

        after = c.get("/metrics").get_data(as_text=True)
        assert "gestalt_build_started" in after
        assert "gestalt_build_completed" in after
        assert "gestalt_eli5_requested" in after

