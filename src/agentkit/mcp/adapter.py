"""Adapt MCP tool descriptors into agentkit ToolSpecs."""

from __future__ import annotations

from typing import Any

from agentkit.protocol.tool_spec import ToolExposure, ToolSpec


def mcp_tool_to_spec(
    raw: dict[str, Any], exposure: ToolExposure = ToolExposure.DIRECT
) -> ToolSpec:
    return ToolSpec(
        name=raw["name"],
        description=raw.get("description", ""),
        parameters=raw.get("input_schema") or {"type": "object", "properties": {}},
        exposure=exposure,
    )
