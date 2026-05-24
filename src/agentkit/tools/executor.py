"""ToolExecutor — the contract every tool implements.

Two equivalent ways to author a tool:
  1. Subclass ToolExecutor and override `spec` + `handle`.
  2. Decorate a function with `@tool` (see decorator.py) — produces a
     ToolExecutor under the hood.

Handlers are always async. Sync functions are wrapped by the decorator.
Returning a plain dict is fine; ToolResult is offered for the cases
where a tool wants to mark itself as failed without raising.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from agentkit.protocol.tool_spec import ToolSpec


@dataclass
class ToolResult:
    """Optional richer return type. Plain dicts are also fine."""

    data: Any = None
    error: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.error is None


class ToolExecutor(ABC):
    """Host code implements this. Framework calls `handle(args)`."""

    spec: ToolSpec

    @abstractmethod
    async def handle(self, arguments: dict[str, Any]) -> Any:  # noqa: D401
        """Run the tool. Return value is forwarded back to the LLM as JSON."""

    @property
    def name(self) -> str:
        return self.spec.name
