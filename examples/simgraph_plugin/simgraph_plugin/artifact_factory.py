"""SimGraphArtifactFactory — graph-shaped UI artifacts.

Contrast with CFDArtifactFactory: that one produced VTK mesh
descriptors. This one produces data cards and subgraph snippets.
Both implement the same ABC and the framework treats them identically.
"""

from __future__ import annotations

from typing import Any

from agentkit.plugin.artifact_factory import ArtifactFactory


class SimGraphArtifactFactory(ArtifactFactory):
    def make(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        result: Any,
    ) -> dict[str, Any] | None:
        if not isinstance(result, dict) or "error" in result:
            return None

        if tool_name == "query_graph":
            return {
                "kind": "result_list",
                "title": f"Search: {arguments.get('question', '?')}",
                "items": result.get("hits", []),
            }

        if tool_name == "get_card":
            return {
                "kind": "data_card",
                "title": f"File {result.get('card', {}).get('path', '?')}",
                "card": result.get("card"),
            }

        if tool_name == "find_similar":
            return {
                "kind": "result_list",
                "title": f"Similar to {arguments.get('file_id')}",
                "items": result.get("neighbors", []),
            }

        if tool_name == "trace_provenance":
            return {
                "kind": "subgraph",
                "title": f"Provenance: {arguments.get('file_id')}",
                "nodes": [result.get("file_id")] + result.get("upstream", []),
                "edges": [
                    (u, result.get("file_id"), "PRODUCES")
                    for u in result.get("upstream", [])
                ],
            }

        return None
