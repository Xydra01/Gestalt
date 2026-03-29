"""
Pydantic schemas for request/response validation.

These are intentionally lightweight: we validate the HTTP boundary so the system fails fast with
clear errors, without trying to fully type every internal payload field.

Feature map (master plan → code):
- `BuildRequest`: accepted by `/build` and `/build/stream` in `app.py`
- `ExplainRequest`: accepted by `/explain` in `app.py` (supports optional `agent_trace`)

Design intent:
Unknown fields are ignored (`extra="ignore"`) so the UI can evolve without breaking the API.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class BuildRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    prompt: str | None = None
    original_prompt: str | None = None
    clarification_answers: str | None = None


class ExplainRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    build: dict[str, Any] = Field(default_factory=dict)
    analysis: dict[str, Any] | None = None
    agent_trace: list[dict[str, Any]] | None = None

