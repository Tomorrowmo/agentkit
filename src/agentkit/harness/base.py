"""Harness — the framework's hook point for safety/policy decisions.

Default Harness allows everything. Host apps subclass or compose
HarnessHook objects to add policy (path whitelisting, payload size
limits, confirmation prompts, etc).

Two hook points only:
  before_call(call)        — may veto the call by returning a verdict
                             with allowed=False
  after_call(call, result) — may inspect result; raise to abort

This is intentionally small. Anything bigger belongs in a host-side
plugin, not the framework.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Iterable, Protocol

from agentkit.protocol.messages import ToolCall


@dataclass
class HarnessVerdict:
    allowed: bool
    reason: str | None = None


class HarnessHook(Protocol):
    async def before_call(self, call: ToolCall) -> HarnessVerdict | None: ...
    async def after_call(self, call: ToolCall, result: Any) -> None: ...


class Harness:
    """Composes a chain of hooks. First veto wins."""

    def __init__(self, hooks: Iterable[HarnessHook] | None = None):
        self.hooks: list[HarnessHook] = list(hooks or [])

    def add_hook(self, hook: HarnessHook) -> None:
        self.hooks.append(hook)

    async def before_call(self, call: ToolCall) -> HarnessVerdict:
        for hook in self.hooks:
            verdict = await hook.before_call(call)
            if verdict is not None and not verdict.allowed:
                return verdict
        return HarnessVerdict(allowed=True)

    async def after_call(self, call: ToolCall, result: Any) -> None:
        for hook in self.hooks:
            await hook.after_call(call, result)


def _allow(call: ToolCall) -> HarnessVerdict | None:  # noqa: ARG001
    return None


async def _noop(call: ToolCall, result: Any) -> None:  # noqa: ARG001
    return None


def make_hook(
    before: Callable[[ToolCall], Awaitable[HarnessVerdict | None]] | None = None,
    after: Callable[[ToolCall, Any], Awaitable[None]] | None = None,
) -> HarnessHook:
    """Convenience: build a HarnessHook from async functions."""

    class _AdHoc:
        async def before_call(self, call: ToolCall) -> HarnessVerdict | None:
            if before is None:
                return None
            return await before(call)

        async def after_call(self, call: ToolCall, result: Any) -> None:
            if after is None:
                return None
            await after(call, result)

    return _AdHoc()
