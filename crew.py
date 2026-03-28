"""Assemble a CrewAI crew from `agents.py` (requires LLM credentials in `.env`)."""

from __future__ import annotations

from pathlib import Path

from crewai import Crew, Process, Task
from dotenv import load_dotenv

from agents import create_auditor_agent, create_synthesizer_agent

_ROOT = Path(__file__).resolve().parent
load_dotenv(_ROOT / ".env")


def build_crew(topic: str = "parts compatibility") -> Crew:
    auditor = create_auditor_agent()
    synthesizer = create_synthesizer_agent()

    audit_task = Task(
        description=(
            f"Review the conceptual model: {topic}. "
            "Assume components declare requires/provides capabilities. "
            "List failure modes when a workspace omits a provider."
        ),
        expected_output="Numbered list of at least 5 specific failure modes.",
        agent=auditor,
    )

    summary_task = Task(
        description=(
            "Using only the prior task context, write a brief readiness checklist "
            "for operators validating a workspace before deploy."
        ),
        expected_output="Markdown checklist, max 8 bullets.",
        agent=synthesizer,
        context=[audit_task],
    )

    return Crew(
        agents=[auditor, synthesizer],
        tasks=[audit_task, summary_task],
        process=Process.sequential,
        verbose=True,
    )


def run_crew(topic: str = "parts compatibility") -> str:
    """Kickoff helper for scripts or future routes."""
    crew = build_crew(topic=topic)
    result = crew.kickoff()
    return str(result)


if __name__ == "__main__":
    print(run_crew())
