"""ArtifactFactory — host-supplied bridge from tool results to UI artifacts.

The framework knows nothing about CFD slices, graphs, charts, etc.
It hands every (tool_name, result) pair to the factory and emits
whatever artifact dict the host returns. Return None to skip.
"""

from __future__ import annotations

from typing import Any


class ArtifactFactory:
    def make(self, tool_name: str, arguments: dict[str, Any], result: Any) -> dict[str, Any] | None:  # noqa: ARG002
        return None
