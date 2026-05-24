"""SimParseArtifactFactory — produce a parse-result card."""

from __future__ import annotations

from typing import Any

from agentkit.plugin.artifact_factory import ArtifactFactory


class SimParseArtifactFactory(ArtifactFactory):
    def make(self, tool_name: str, arguments: dict[str, Any], result: Any):
        if not isinstance(result, dict) or "error" in result:
            return None

        if tool_name in ("auto_parse", "parse_cgns", "parse_openfoam", "parse_fluent"):
            return {
                "kind": "parse_card",
                "title": f"{result.get('solver')} parse — {arguments.get('path')}",
                "solver": result.get("solver"),
                "metadata": result.get("metadata") or {},
                "file_count": result.get("file_count"),
            }

        if tool_name == "list_parsers":
            return {
                "kind": "parser_table",
                "title": "Supported solver parsers",
                "rows": result.get("parsers", []),
            }

        return None
