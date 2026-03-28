"""Example custom tool — replace or extend with real integrations."""

from typing import Type

from crewai.tools import BaseTool
from pydantic import BaseModel, Field


class CustomToolInput(BaseModel):
    """Inputs for the example tool."""

    query: str = Field(..., description="Short description of what to look up.")


class CustomTool(BaseTool):
    name: str = "gestalt_example_tool"
    description: str = (
        "Example placeholder tool. Replace with domain-specific logic "
        "and wire into agents in crew.py."
    )
    args_schema: Type[BaseModel] = CustomToolInput

    def _run(self, query: str) -> str:
        return f"[placeholder] Received query: {query!r}"
