from __future__ import annotations

from crew import (
    add_confidence_scores,
    apply_hard_constraints_to_build,
    extract_hard_part_constraints,
)


def test_extract_hard_part_constraints_cpu_gpu_ram_psu_case() -> None:
    prompt = (
        "Build me a gaming PC for $1200. Use an NVIDIA RTX 4070 and an AMD Ryzen 5 7600X. "
        "Include 32GB RAM, a 750W PSU, and a mid tower case."
    )
    hard = extract_hard_part_constraints(prompt)
    assert hard["gpu"] in ("rtx 4070", "rtx 4070")
    assert "ryzen 5" in hard["cpu"]
    assert hard["ram"] == "32gb"
    assert hard["psu"] == "750w"
    assert hard["case"] == "mid tower"


def test_apply_hard_constraints_overrides_build_when_match_exists() -> None:
    parts_data = {
        "cpus": [{"id": "c1", "name": "AMD Ryzen 5 7600X", "price": 200}],
        "gpus": [
            {"id": "g1", "name": "AMD Radeon RX 7800 XT", "price": 450},
            {"id": "g2", "name": "NVIDIA GeForce RTX 4070", "price": 550},
        ],
        "motherboards": [{"id": "m1", "name": "B650 board", "price": 150}],
        "ram": [{"id": "r1", "name": "32GB DDR5 kit", "price": 100}],
        "psus": [{"id": "p1", "name": "750W Gold PSU", "price": 90}],
        "cases": [{"id": "case1", "name": "Mid Tower Case", "price": 70}],
    }
    build = {
        "cpu": parts_data["cpus"][0],
        "gpu": parts_data["gpus"][0],  # wrong on purpose
        "motherboard": parts_data["motherboards"][0],
        "ram": parts_data["ram"][0],
        "psu": parts_data["psus"][0],
        "case": parts_data["cases"][0],
    }
    hard = {"gpu": "rtx 4070"}
    out, applied = apply_hard_constraints_to_build(build, parts_data, hard)
    assert out["gpu"]["id"] == "g2"
    assert applied and applied[0]["slot"] == "gpu"


def test_add_confidence_scores_attaches_confidence() -> None:
    build = {
        "cpu": {"id": "c1", "name": "AMD Ryzen 5 7600X", "price": 200},
        "gpu": {"id": "g2", "name": "NVIDIA GeForce RTX 4070", "price": 550},
        "motherboard": {"id": "m1", "name": "B650 board", "price": 150},
        "ram": {"id": "r1", "name": "32GB DDR5 kit", "price": 100},
        "psu": {"id": "p1", "name": "750W Gold PSU", "price": 90},
        "case": {"id": "case1", "name": "Mid Tower Case", "price": 70},
    }
    hard = {"cpu": "ryzen 5 7600x", "gpu": "rtx 4070"}
    rules_usd = {"cpu": 240.0, "gpu": 480.0, "mobo": 180.0, "ram": 120.0, "psu": 120.0, "case": 60.0}
    out = add_confidence_scores(build, hard=hard, rules_usd=rules_usd)
    assert "confidence" in out["cpu"]
    assert 0.0 <= out["cpu"]["confidence"]["score"] <= 1.0
    assert isinstance(out["cpu"]["confidence"]["reasons"], list)

