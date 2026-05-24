"""ToolRouter — dispatches a ToolCall to its executor with hooks in the loop.

Failure modes are surfaced as dict payloads (not raised) so the LLM can
see what went wrong and self-correct. Hard errors (registry miss,
harness reject) are raised.
"""

from __future__ import annotations

from typing import Any

from agentkit.harness.base import Harness
from agentkit.observability.trace import Tracer
from agentkit.protocol.errors import HarnessRejected, ToolError, ToolNotFound
from agentkit.protocol.messages import ToolCall
from agentkit.tools.executor import ToolResult
from agentkit.tools.registry import ToolRegistry


def _result_to_payload(value: Any) -> Any:
    if isinstance(value, ToolResult):
        return {"data": value.data, "error": value.error, "meta": value.meta}
    return value


class ToolRouter:
    def __init__(
        self,
        registry: ToolRegistry,
        harness: Harness | None = None,
        tracer: Tracer | None = None,
    ):
        self.registry = registry
        self.harness = harness or Harness()
        self.tracer = tracer or Tracer()

    async def dispatch(self, call: ToolCall) -> Any:
        executor = self.registry.get(call.name)
        if executor is None:
            raise ToolNotFound(call.name)

        verdict = await self.harness.before_call(call)
        if not verdict.allowed:
            raise HarnessRejected(verdict.reason or "harness rejected")

        with self.tracer.span("tool_call", name=call.name, call_id=call.id) as span:
            try:
                raw = await executor.handle(call.arguments)
            except Exception as exc:  # noqa: BLE001
                span.error = str(exc)
                raise ToolError(call.name, exc) from exc
            payload = _result_to_payload(raw)
            await self.harness.after_call(call, payload)
            span.result_meta = {"size": _size_hint(payload)}
            return payload


def _size_hint(value: Any) -> int:
    try:
        return len(repr(value))
    except Exception:  # noqa: BLE001
        return -1
