"""ToolSpec — what the LLM sees when picking a tool.

Schema is a JSON-schema dict (not Pydantic). The decision is deliberate:
LLM providers all speak JSON schema, and forcing host apps to declare a
Pydantic model for every tool would be friction without payoff. The
@tool decorator can still derive schema from type hints.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ToolExposure(str, Enum):
    """How the tool appears to the LLM.

    DIRECT     — always in the prompt.
    DEFERRED   — name visible via tool_search; schema loaded on demand.
    HIDDEN     — not visible to the LLM; callable only by other code.
    """

    DIRECT = "direct"
    DEFERRED = "deferred"
    HIDDEN = "hidden"


class ToolSpec(BaseModel):
    name: str
    description: str
    parameters: dict[str, Any] = Field(
        default_factory=lambda: {"type": "object", "properties": {}}
    )
    exposure: ToolExposure = ToolExposure.DIRECT
