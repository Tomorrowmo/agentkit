"""sim_parse harness — keep parsers off paths outside the configured root."""

from __future__ import annotations

import os
from pathlib import Path

from agentkit.harness.base import HarnessVerdict, make_hook
from agentkit.protocol.messages import ToolCall


def _root() -> Path:
    return Path(os.environ.get("SIM_PARSE_ROOT", os.getcwd())).resolve()


async def _check(call: ToolCall) -> HarnessVerdict | None:
    if call.name not in ("detect_format", "auto_parse", "parse_cgns", "parse_openfoam", "parse_fluent"):
        return None
    path = call.arguments.get("path")
    if not isinstance(path, str):
        return None
    try:
        p = Path(path).resolve()
    except (OSError, ValueError):
        return HarnessVerdict(allowed=False, reason=f"invalid path: {path}")
    root = _root()
    if root not in p.parents and p != root:
        return HarnessVerdict(allowed=False, reason=f"path outside SIM_PARSE_ROOT: {path}")
    return None


sim_parse_harness_hook = make_hook(before=_check)
