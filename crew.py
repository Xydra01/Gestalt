"""Gestalt PC build crew — skeleton with mock parts/validation until data layer lands."""

from __future__ import annotations

import json
import os
from pathlib import Path

from crewai import Crew, Process, Task
from dotenv import load_dotenv

from agents import analysis_agent, recommendation_agent

# --- Temporary mocks (hackathon): remove when real load_parts / validate_build exist ---


def load_parts() -> dict:
    """Mock catalog until parts.json + loader are wired."""
    return {
        "cpus": [{"id": "c1", "price": 200, "socket": "AM5", "tdp": 105}],
        "gpus": [{"id": "g1", "price": 400, "tdp": 200, "length_mm": 300}],
        "motherboards": [{"id": "m1", "price": 150, "socket": "AM5", "ddr_support": "DDR5"}],
        "ram": [{"id": "r1", "price": 80, "ddr_gen": "DDR5"}],
        "psus": [{"id": "p1", "price": 100, "wattage": 750}],
        "cases": [{"id": "case1", "price": 90, "max_gpu_length_mm": 350}],
    }


def validate_build(build: dict) -> dict:
    """Mock validator; returns checker-shaped result until compatibility_checker.validate_build is used."""
    _ = build
    return {"passed": True, "errors": []}


# -----------------------------------------------------------------------------------------

_ROOT = Path(__file__).resolve().parent
load_dotenv(_ROOT / ".env")


def run_build_assistant(user_input: str) -> str:
    """
    PC build assistant entrypoint (skeleton).

    Will orchestrate: Analysis → Recommendation → Validation (with retry loop, max 3).
    """
    _ = json.dumps(load_parts())
    _ = os.environ.get("OPENAI_API_KEY", "")
    _ = validate_build({})
    _ = user_input
    # TODO: wire Task chain, crew.kickoff(), feed validate_build errors back to recommendation
    return json.dumps(
        {
            "status": "skeleton",
            "message": "Agent pipeline not fully wired; mocks in place for parts/validation.",
        }
    )


def build_crew(topic: str = "parts compatibility") -> Crew:
    """Minimal sequential crew using analysis + recommendation agents (for LLM smoke tests)."""
    a = analysis_agent()
    r = recommendation_agent()
    t1 = Task(
        description=f"Topic context: {topic}. Summarize as JSON placeholder.",
        expected_output="Short JSON string",
        agent=a,
    )
    t2 = Task(
        description="Using prior context, output OK.",
        expected_output="OK",
        agent=r,
        context=[t1],
    )
    return Crew(agents=[a, r], tasks=[t1, t2], process=Process.sequential, verbose=True)


def run_crew(topic: str = "parts compatibility") -> str:
    crew = build_crew(topic=topic)
    return str(crew.kickoff())


if __name__ == "__main__":
    print(run_build_assistant("Build me a gaming PC for $1000"))
