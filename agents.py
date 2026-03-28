"""CrewAI agent definitions for Gestalt."""

from __future__ import annotations

from crewai import Agent


def create_auditor_agent() -> Agent:
    return Agent(
        role="Parts compatibility auditor",
        goal="Identify missing capabilities and risky part combinations.",
        backstory=(
            "You analyze component graphs and surface concrete conflicts, "
            "never hand-waving with generic advice."
        ),
        verbose=True,
    )


def create_synthesizer_agent() -> Agent:
    return Agent(
        role="Integration synthesizer",
        goal="Turn audit notes into a short, actionable summary.",
        backstory="You write crisp markdown for engineers who ship systems.",
        verbose=True,
    )
