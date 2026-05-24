"""sim_cli harness — binary whitelist for the spawned executable."""

from __future__ import annotations

import os

from agentkit.harness.base import HarnessVerdict, make_hook
from agentkit.protocol.messages import ToolCall


ALLOWED_BINARIES = {"simgraph", "simgraph.exe"}


async def _check(call: ToolCall) -> HarnessVerdict | None:
    # Only the spawning tools need policy here; status/version are read-only
    if call.name not in (
        "start_collector",
        "start_mcp",
        "start_post_service",
        "init_config",
        "cli_version",
    ):
        return None
    # The tool itself constructs argv; harness has nothing to inspect at
    # call time (argv is computed inside the tool). Keep this hook as a
    # placeholder showing where a real policy (custom binary path) would
    # plug in: read os.environ['SIMGRAPH_BIN'] and compare.
    if "SIMGRAPH_BIN" in os.environ:
        bin_name = os.path.basename(os.environ["SIMGRAPH_BIN"])
        if bin_name not in ALLOWED_BINARIES:
            return HarnessVerdict(
                allowed=False, reason=f"SIMGRAPH_BIN points to {bin_name}, not in whitelist"
            )
    return None


simgraph_cli_harness_hook = make_hook(before=_check)
