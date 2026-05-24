"""SimGraph harness — reject ingest of paths outside the index root."""

from __future__ import annotations

from pathlib import Path

from agentkit.harness.base import HarnessVerdict, make_hook
from agentkit.protocol.messages import ToolCall

from simgraph_plugin.tools import index_root


async def _check(call: ToolCall) -> HarnessVerdict | None:
    if call.name != "ingest_file":
        return None
    path = call.arguments.get("path")
    if not isinstance(path, str):
        return None
    root = index_root()
    try:
        p = Path(path).resolve()
    except (OSError, ValueError):
        return HarnessVerdict(allowed=False, reason=f"invalid path: {path}")
    # Allow if the path is under root OR if root doesn't exist (demo on dev box).
    if not root.exists():
        return None
    if root not in p.parents and p != root:
        return HarnessVerdict(allowed=False, reason=f"path outside index root: {path}")
    return None


simgraph_harness_hook = make_hook(before=_check)
