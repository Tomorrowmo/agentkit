"""MCPProxyExecutor — a ToolExecutor that forwards to an MCP server.

This is how remote tools enter the local registry: list_tools from the
MCP server, adapt each entry into a ToolSpec, and wrap one of these
around it. Calls then transparently round-trip over the MCP transport.
"""

from __future__ import annotations

from typing import Any

from agentkit.mcp.client import MCPClient
from agentkit.protocol.tool_spec import ToolSpec
from agentkit.tools.executor import ToolExecutor


class MCPProxyExecutor(ToolExecutor):
    def __init__(self, client: MCPClient, spec: ToolSpec):
        self.client = client
        self.spec = spec

    async def handle(self, arguments: dict[str, Any]) -> Any:
        return await self.client.call_tool(self.spec.name, arguments)
