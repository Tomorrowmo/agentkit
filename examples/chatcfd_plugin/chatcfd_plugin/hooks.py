"""CFD-specific hooks.

CFDMemoryHook — example ContextHook. In real chatcfd this would call
mempalace to recall context related to the user's message and prepend
it as a system reminder. Here it just demonstrates the lifecycle.

cfd_harness_hook — example HarnessHook. Rejects any tool call whose
arguments reference a path outside the configured case root. Real
chatcfd has a richer policy (file size, file type, etc.) but the
extension surface is the same.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agentkit.harness.base import HarnessVerdict, make_hook
from agentkit.plugin.context_hooks import ContextHook
from agentkit.protocol.messages import ToolCall
from agentkit.session.thread import Thread

from chatcfd_plugin.prompt_builder import CFDState
from chatcfd_plugin.tools import case_root


class CFDMemoryHook(ContextHook):
    """Demonstrates before/after_turn shape. Real impl calls mempalace."""

    async def before_turn(self, thread: Thread, user_message: str) -> None:
        thread.metadata.setdefault("cfd_state", CFDState())
        # Real impl: hits memory store, prepends a "recalled context" system msg
        # to thread.messages. We keep it a no-op so the demo stays runnable.
        return None

    async def after_turn(self, thread: Thread) -> None:
        # Real impl: scans the latest assistant message for facts/decisions and
        # writes them to memory.
        return None


def _looks_pathy(s: Any) -> bool:
    if not isinstance(s, str):
        return False
    return "/" in s or "\\" in s


def _outside_case_root(value: str) -> bool:
    root = case_root()
    try:
        p = Path(value).resolve()
    except (OSError, ValueError):
        return True
    return root not in p.parents and p != root


async def _whitelist(call: ToolCall) -> HarnessVerdict | None:
    for v in call.arguments.values():
        if _looks_pathy(v) and _outside_case_root(v):
            return HarnessVerdict(
                allowed=False,
                reason=f"path outside case root: {v}",
            )
    return None


cfd_harness_hook = make_hook(before=_whitelist)
