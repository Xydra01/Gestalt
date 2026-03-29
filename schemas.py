"""
Pydantic schemas for request/response validation.

These are intentionally lightweight: we validate the HTTP boundary so the system fails fast with
clear errors, without trying to fully type every internal payload field.
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

