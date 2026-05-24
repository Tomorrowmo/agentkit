"""ToolSearch — the deferred-tool gateway.

When tool count grows past what fits in a system prompt, mark less
common tools as DEFERRED. They stay invisible until the LLM calls
`tool_search`, which returns matching specs that the host can then load
into the next turn.

This module exposes the function. Wiring it into a registry as a real
tool is the host's job (see plugin/app.py for the default wire-up).
"""

from __future__ import annotations

from agentkit.protocol.tool_spec import ToolExposure, ToolSpec
from agentkit.tools.registry import ToolRegistry


class ToolSearch:
    def __init__(self, registry: ToolRegistry):
        self.registry = registry

    def search(self, query: str, limit: int = 5) -> list[ToolSpec]:
        q = query.lower().strip()
        scored: list[tuple[int, ToolSpec]] = []
        for spec in self.registry.all_specs():
            if spec.exposure != ToolExposure.DEFERRED:
                continue
            score = self._score(spec, q)
            if score > 0:
                scored.append((score, spec))
        scored.sort(key=lambda kv: kv[0], reverse=True)
        return [s for _, s in scored[:limit]]

    @staticmethod
    def _score(spec: ToolSpec, q: str) -> int:
        if not q:
            return 1
        hay = (spec.name + " " + spec.description).lower()
        return sum(1 for token in q.split() if token in hay)
