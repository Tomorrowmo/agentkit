"""SimCliArtifactFactory — process-table artifacts."""

from __future__ import annotations

from typing import Any

from agentkit.plugin.artifact_factory import ArtifactFactory


class SimCliArtifactFactory(ArtifactFactory):
    def make(self, tool_name: str, arguments: dict[str, Any], result: Any):
        if not isinstance(result, dict) or "error" in result:
            return None

        if tool_name == "cli_status":
            return {
                "kind": "process_table",
                "title": "simgraph processes",
                "procs": result.get("procs", []),
            }

        if tool_name in ("start_collector", "start_mcp", "start_post_service"):
            return {
                "kind": "process_started",
                "title": f"started: {tool_name}",
                "argv": result.get("argv"),
                "pid": result.get("pid"),
            }

        return None
