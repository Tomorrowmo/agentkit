"""EvalSetupHook — declarative case-state seeding.

Problem: an eval case often needs the plugin to be in a particular
state before the LLM runs (e.g. "the collector is already running",
"these three files are already in the graph"). Hard-coding this in
each plugin's test_evals.py was the M5 shortcut. M6 formalizes it.

Pattern: plugin registers SetupHooks that key off case.setup keys.
Runner calls them in order before each case.

Example plugin registration:

    from agentkit.eval.setup import setup_hook

    @setup_hook("pre_running")
    async def _pre_running(value, ctx):
        for name in value:
            process_registry.add(name, ["simgraph", "c"], pid=12345)

The hook receives the value of case.setup["pre_running"] and an
AppContext (for access to registry / threads / etc).
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from agentkit.plugin.app import AppContext


HookFn = Callable[[Any, AppContext], Awaitable[None] | None]


@dataclass
class SetupHook:
    key: str
    fn: HookFn
    teardown: HookFn | None = None


class SetupRegistry:
    """Process-wide registry of setup hooks. Keyed by setup-dict key."""

    def __init__(self) -> None:
        self._hooks: dict[str, list[SetupHook]] = {}

    def register(self, hook: SetupHook) -> None:
        self._hooks.setdefault(hook.key, []).append(hook)

    def clear(self) -> None:
        self._hooks.clear()

    def hooks_for(self, setup_dict: dict[str, Any]) -> list[tuple[SetupHook, Any]]:
        out: list[tuple[SetupHook, Any]] = []
        for key, value in setup_dict.items():
            for h in self._hooks.get(key, []):
                out.append((h, value))
        return out

    async def apply(self, setup_dict: dict[str, Any], ctx: AppContext) -> list[SetupHook]:
        """Run setup hooks in registration order. Returns hooks needing teardown."""
        applied: list[SetupHook] = []
        for hook, value in self.hooks_for(setup_dict):
            res = hook.fn(value, ctx)
            if inspect.isawaitable(res):
                await res
            applied.append(hook)
        return applied

    async def teardown(self, applied: list[SetupHook], ctx: AppContext) -> None:
        for hook in reversed(applied):
            if hook.teardown is None:
                continue
            res = hook.teardown(None, ctx)
            if inspect.isawaitable(res):
                await res


# Default process-wide registry. Plugins may build their own if isolation
# matters (e.g. running two eval suites in the same pytest process).
DEFAULT_REGISTRY = SetupRegistry()


def setup_hook(
    key: str,
    teardown: HookFn | None = None,
    registry: SetupRegistry | None = None,
) -> Callable[[HookFn], HookFn]:
    """Decorator: register a setup hook for a given case.setup key.

        @setup_hook("pre_running")
        async def seed(value, ctx): ...
    """

    def wrap(fn: HookFn) -> HookFn:
        reg = registry or DEFAULT_REGISTRY
        reg.register(SetupHook(key=key, fn=fn, teardown=teardown))
        return fn

    return wrap
