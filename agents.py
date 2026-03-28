"""CrewAI agent definitions for Gestalt (PC Builder AI)."""

from __future__ import annotations

from crewai import Agent

# Exact prompts from Project_Plan.txt (Phase 2.1) — {user_input} / {analysis} / {error} are
# filled by task descriptions when the crew is wired.

_ANALYSIS_PROMPT = """You are a PC building analyst. Given a user's request, extract:
1. Total budget in USD
2. Primary use case (gaming / creative work / general productivity / development)
3. Performance priority (max fps / max quality / balanced)
4. Any stated preferences or constraints

Return ONLY a JSON object:
{
  "budget": <number>,
  "use_case": <string>,
  "priority": <string>,
  "constraints": [<string>]
}

User request: {user_input}"""

_RECOMMENDATION_PROMPT = """You are a PC parts selector. You have access to parts.json.
Given this build analysis: {analysis}
And this validation error (if any): {error}

Select one part from each category that:
- Fits within the budget allocation
- Matches the use case tier
- Does NOT repeat any part that previously caused a validation error

Budget allocation rules:
- Gaming: 40% GPU, 20% CPU, 15% mobo, 10% RAM, 10% PSU, 5% case
- Creative: 25% GPU, 30% CPU, 15% mobo, 15% RAM, 10% PSU, 5% case
- General: 15% GPU, 35% CPU, 20% mobo, 15% RAM, 10% PSU, 5% case

Return ONLY a JSON object with selected part IDs."""


def analysis_agent() -> Agent:
    """Agent 1 – Analysis: parse user request into structured JSON."""
    return Agent(
        role="PC building analyst",
        goal=(
            "Follow your instructions exactly: output ONLY the JSON schema described in your backstory."
        ),
        backstory=_ANALYSIS_PROMPT,
        verbose=True,
    )


def recommendation_agent() -> Agent:
    """Agent 2 – Recommendation: select part IDs from parts.json given analysis and errors."""
    return Agent(
        role="PC parts selector",
        goal=(
            "Follow your instructions exactly: output ONLY a JSON object of selected part IDs."
        ),
        backstory=_RECOMMENDATION_PROMPT,
        verbose=True,
    )
