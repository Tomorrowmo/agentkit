"""MCPClient — one connection to one MCP server.

Wraps the official `mcp` SDK. Supports SSE (URL) and stdio (command +
args). Lifecycle is connect → list_tools → call_tool*. Reconnect is
handled by MCPPool, not here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class MCPServerConfig:
    name: str
    transport: Literal["sse", "stdio"] = "sse"
    url: str | None = None                    # for transport=sse
    command: str | None = None                # for transport=stdio
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)


class MCPClient:
    """Single MCP session. Implementation kept thin — most logic lives
    in the official SDK; this class is mostly lifecycle bookkeeping."""

    def __init__(self, config: MCPServerConfig):
        self.config = config
        self._session: Any = None
        self._exit_stack: Any = None
        self._tools_cache: list[dict[str, Any]] | None = None

    async def connect(self) -> None:
        from contextlib import AsyncExitStack

        from mcp import ClientSession
        from mcp.client.sse import sse_client
        from mcp.client.stdio import StdioServerParameters, stdio_client

        stack = AsyncExitStack()
        await stack.__aenter__()

        if self.config.transport == "sse":
            if not self.config.url:
                raise ValueError(f"{self.config.name}: url required for SSE")
            read, write = await stack.enter_async_context(sse_client(self.config.url))
        else:
            if not self.config.command:
                raise ValueError(f"{self.config.name}: command required for stdio")
            params = StdioServerParameters(
                command=self.config.command,
                args=self.config.args,
                env=self.config.env or None,
            )
            read, write = await stack.enter_async_context(stdio_client(params))

        session = await stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        self._session = session
        self._exit_stack = stack

    async def close(self) -> None:
        if self._exit_stack is not None:
            await self._exit_stack.__aexit__(None, None, None)
            self._exit_stack = None
            self._session = None

    async def list_tools(self, force_refresh: bool = False) -> list[dict[str, Any]]:
        if self._session is None:
            raise RuntimeError(f"{self.config.name}: not connected")
        if self._tools_cache is not None and not force_refresh:
            return self._tools_cache
        result = await self._session.list_tools()
        tools = []
        for t in result.tools:
            tools.append(
                {
                    "name": t.name,
                    "description": t.description or "",
                    "input_schema": t.inputSchema or {"type": "object", "properties": {}},
                }
            )
        self._tools_cache = tools
        return tools

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        if self._session is None:
            raise RuntimeError(f"{self.config.name}: not connected")
        result = await self._session.call_tool(name, arguments)
        # Reduce MCP CallToolResult to a JSON-friendly shape.
        parts: list[Any] = []
        for c in getattr(result, "content", []) or []:
            text = getattr(c, "text", None)
            if text is not None:
                parts.append(text)
            else:
                parts.append(getattr(c, "model_dump", lambda: str(c))())
        if len(parts) == 1:
            return parts[0]
        return parts
