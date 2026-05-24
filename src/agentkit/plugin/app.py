"""App — what a host application instantiates.

Wires the protocol / tools / mcp / session / llm / harness / skills /
observability / ipc layers together. Hosts pass their own
PromptBuilder / ArtifactFactory / ContextHooks / tools / mcp_servers.

App.run() starts a uvicorn server with the WebSocket endpoint mounted.
App.turn(thread, message) drives one full LLM ↔ tool round-trip and
yields StreamEvents — IPC layer translates events into wire frames.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, AsyncIterator, Iterable, Sequence

from agentkit.harness.base import Harness
from agentkit.llm.client import LLMClient
from agentkit.mcp.client import MCPServerConfig
from agentkit.mcp.pool import MCPPool
from agentkit.observability.insight_log import InsightLog
from agentkit.observability.trace import Tracer
from agentkit.plugin.artifact_factory import ArtifactFactory
from agentkit.plugin.context_hooks import ContextHook
from agentkit.plugin.prompt_builder import PromptBuilder
from agentkit.protocol.errors import HarnessRejected, ToolError, ToolNotFound
from agentkit.protocol.events import (
    ArtifactEvent,
    AssistantTextEvent,
    ErrorEvent,
    StreamEvent,
    ThreadStartedEvent,
    ToolCallEvent,
    ToolResultEvent,
    TurnFinishedEvent,
)
from agentkit.protocol.tool_spec import ToolExposure
from agentkit.session.pool import ThreadPool
from agentkit.session.thread import Thread
from agentkit.session.turn import TurnContext
from agentkit.tools.registry import ToolRegistry
from agentkit.tools.router import ToolRouter

MAX_TOOL_ROUNDS = 10


@dataclass
class AppContext:
    """The bag of singletons. Plugins receive this on init if needed."""

    registry: ToolRegistry
    router: ToolRouter
    threads: ThreadPool
    llm: LLMClient
    harness: Harness
    tracer: Tracer
    log: InsightLog | None


class App:
    def __init__(
        self,
        *,
        tools: ToolRegistry | Iterable[Any] | None = None,
        mcp_servers: Sequence[MCPServerConfig] | Sequence[str] | None = None,
        llm: LLMClient | None = None,
        harness: Harness | None = None,
        prompt_builder: PromptBuilder | None = None,
        artifact_factory: ArtifactFactory | None = None,
        context_hooks: Iterable[ContextHook] | None = None,
        insight_log_path: str | None = None,
    ):
        self.registry = _coerce_registry(tools)
        self.mcp_configs = _coerce_mcp(mcp_servers)
        self.llm = llm or LLMClient()
        self.harness = harness or Harness()
        self.prompt_builder = prompt_builder or PromptBuilder()
        self.artifact_factory = artifact_factory or ArtifactFactory()
        self.context_hooks: list[ContextHook] = list(context_hooks or [])
        self.tracer = Tracer()
        self.log = InsightLog(insight_log_path) if insight_log_path else None
        self.threads = ThreadPool()
        self.router = ToolRouter(self.registry, self.harness, self.tracer)
        self._mcp_pool: MCPPool | None = None

    @property
    def context(self) -> AppContext:
        return AppContext(
            registry=self.registry,
            router=self.router,
            threads=self.threads,
            llm=self.llm,
            harness=self.harness,
            tracer=self.tracer,
            log=self.log,
        )

    async def startup(self) -> None:
        if self.mcp_configs:
            self._mcp_pool = MCPPool(self.mcp_configs)
            await self._mcp_pool.connect_all(self.registry)

    async def shutdown(self) -> None:
        if self._mcp_pool is not None:
            await self._mcp_pool.close_all()
            self._mcp_pool = None

    async def turn(
        self,
        thread: Thread,
        user_message: str,
    ) -> AsyncIterator[StreamEvent]:
        for hook in self.context_hooks:
            await hook.before_turn(thread, user_message)

        thread.set_system(self.prompt_builder.build(thread))
        thread.add_user(user_message)

        ctx = TurnContext(thread=thread)
        specs = self.registry.specs(exposure=ToolExposure.DIRECT)

        for round_idx in range(MAX_TOOL_ROUNDS):
            if ctx.cancelled:
                break

            try:
                resp = await self.llm.complete(thread.messages, tools=specs)
            except Exception as exc:  # noqa: BLE001
                yield ErrorEvent(message=f"llm error: {exc}")
                break

            thread.add_assistant(resp.message)

            if resp.message.content:
                yield AssistantTextEvent(delta=resp.message.content)

            if not resp.message.tool_calls:
                break

            for call in resp.message.tool_calls:
                yield ToolCallEvent(
                    call_id=call.id, name=call.name, arguments=call.arguments
                )
                try:
                    result = await self.router.dispatch(call)
                    yield ToolResultEvent(
                        call_id=call.id, name=call.name, result=_summarize(result)
                    )
                    self._maybe_log("tool_result", call=call.name, ok=True)
                    artifact = self.artifact_factory.make(call.name, call.arguments, result)
                    if artifact is not None:
                        yield ArtifactEvent(
                            kind=str(artifact.get("kind", "generic")), payload=artifact
                        )
                    thread.add_tool_result(call.id, call.name, _to_text(result))
                except (ToolError, ToolNotFound, HarnessRejected) as exc:
                    err = str(exc)
                    yield ToolResultEvent(call_id=call.id, name=call.name, error=err)
                    self._maybe_log("tool_result", call=call.name, ok=False, error=err)
                    thread.add_tool_result(call.id, call.name, json.dumps({"error": err}))

            if round_idx == MAX_TOOL_ROUNDS - 1:
                yield ErrorEvent(message=f"max tool rounds ({MAX_TOOL_ROUNDS}) exceeded")

        for hook in self.context_hooks:
            await hook.after_turn(thread)

        yield TurnFinishedEvent(thread_id=thread.id)

    def open_thread(self, thread_id: str | None = None) -> Thread:
        return self.threads.get_or_create(thread_id)

    def started_event(self, thread: Thread) -> ThreadStartedEvent:
        return ThreadStartedEvent(thread_id=thread.id)

    def run(self, host: str = "127.0.0.1", port: int = 8765) -> None:
        from agentkit.runtime.server import build_asgi

        import uvicorn

        asgi = build_asgi(self)
        asyncio.run(self._run_with_lifespan(asgi, host, port, uvicorn))

    async def _run_with_lifespan(self, asgi: Any, host: str, port: int, uvicorn_mod: Any) -> None:
        await self.startup()
        try:
            config = uvicorn_mod.Config(asgi, host=host, port=port, log_level="info")
            server = uvicorn_mod.Server(config)
            await server.serve()
        finally:
            await self.shutdown()

    def _maybe_log(self, event_type: str, **fields: Any) -> None:
        if self.log is not None:
            self.log.write({"type": event_type, **fields})


def _coerce_registry(tools: ToolRegistry | Iterable[Any] | None) -> ToolRegistry:
    if isinstance(tools, ToolRegistry):
        return tools
    if tools is None:
        return ToolRegistry()
    reg = ToolRegistry()
    for t in tools:
        reg.register(t)
    return reg


def _coerce_mcp(
    sources: Sequence[MCPServerConfig] | Sequence[str] | None,
) -> list[MCPServerConfig]:
    if not sources:
        return []
    out: list[MCPServerConfig] = []
    for s in sources:
        if isinstance(s, MCPServerConfig):
            out.append(s)
        elif isinstance(s, str):
            out.append(MCPServerConfig(name=s, transport="sse", url=s))
        else:
            raise TypeError(f"unsupported mcp source: {s!r}")
    return out


def _summarize(result: Any, max_len: int = 2000) -> Any:
    text = _to_text(result)
    if len(text) <= max_len:
        return result
    return {"_truncated": True, "preview": text[:max_len], "full_len": len(text)}


def _to_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except TypeError:
        return str(value)
