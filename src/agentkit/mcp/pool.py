"""MCPPool — owns N MCP clients and discovers their tools into a registry.

Usage:

    pool = MCPPool([MCPServerConfig(name="post", url="http://localhost:8000/sse")])
    await pool.connect_all(registry)   # registers proxies in `registry`
    ...
    await pool.close_all()

Reconnect is best-effort: if a tool call fails, the caller can call
`pool.reconnect(name)` and retry. Active health-checking is intentionally
omitted; revisit if hosts ask for it.
"""

from __future__ import annotations

from typing import Iterable

from agentkit.mcp.adapter import mcp_tool_to_spec
from agentkit.mcp.client import MCPClient, MCPServerConfig
from agentkit.mcp.proxy_executor import MCPProxyExecutor
from agentkit.protocol.tool_spec import ToolExposure
from agentkit.tools.registry import ToolRegistry


class MCPPool:
    def __init__(self, configs: Iterable[MCPServerConfig]):
        self._configs = {c.name: c for c in configs}
        self._clients: dict[str, MCPClient] = {}

    async def connect_all(
        self,
        registry: ToolRegistry,
        exposure: ToolExposure = ToolExposure.DIRECT,
    ) -> None:
        for name, cfg in self._configs.items():
            client = MCPClient(cfg)
            await client.connect()
            self._clients[name] = client
            for raw in await client.list_tools():
                spec = mcp_tool_to_spec(raw, exposure=exposure)
                if registry.has(spec.name):
                    continue  # local tool wins on name clash
                registry.register(MCPProxyExecutor(client, spec))

    async def reconnect(self, name: str) -> None:
        client = self._clients.get(name)
        if client is not None:
            await client.close()
        cfg = self._configs[name]
        client = MCPClient(cfg)
        await client.connect()
        self._clients[name] = client

    async def close_all(self) -> None:
        for client in self._clients.values():
            try:
                await client.close()
            except Exception:  # noqa: BLE001
                pass
        self._clients.clear()
