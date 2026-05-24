"""ToolRegistry — the canonical place tools live.

Holds ToolExecutor instances by name. Selects which specs to surface to
the LLM based on ToolExposure. Iteration order matches insertion order.
"""

from __future__ import annotations

from typing import Iterable, Iterator

from agentkit.protocol.tool_spec import ToolExposure, ToolSpec
from agentkit.tools.executor import ToolExecutor


class ToolRegistry:
    def __init__(self, executors: Iterable[ToolExecutor] | None = None):
        self._tools: dict[str, ToolExecutor] = {}
        for ex in executors or ():
            self.register(ex)

    def register(self, executor: ToolExecutor) -> None:
        name = executor.spec.name
        if name in self._tools:
            raise ValueError(f"duplicate tool name: {name}")
        self._tools[name] = executor

    def unregister(self, name: str) -> None:
        self._tools.pop(name, None)

    def get(self, name: str) -> ToolExecutor | None:
        return self._tools.get(name)

    def has(self, name: str) -> bool:
        return name in self._tools

    def __iter__(self) -> Iterator[ToolExecutor]:
        return iter(self._tools.values())

    def __len__(self) -> int:
        return len(self._tools)

    def specs(
        self, exposure: ToolExposure | None = ToolExposure.DIRECT
    ) -> list[ToolSpec]:
        """Return tool specs filtered by exposure. None = all."""
        out: list[ToolSpec] = []
        for ex in self._tools.values():
            if exposure is None or ex.spec.exposure == exposure:
                out.append(ex.spec)
        return out

    def all_specs(self) -> list[ToolSpec]:
        return [ex.spec for ex in self._tools.values()]
