"""Smoke tests — no LLM key required.

These exercise every framework layer that does not require a network
call, end-to-end. If these pass, the abstractions hold together; the
remaining failure modes are provider-specific (LLM / MCP server).
"""

from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from agentkit import App, tool
from agentkit.harness.base import Harness, HarnessVerdict, make_hook
from agentkit.protocol.errors import HarnessRejected, ToolError, ToolNotFound
from agentkit.protocol.messages import AssistantMessage, ToolCall
from agentkit.runtime.server import build_asgi
from agentkit.session.thread import Thread
from agentkit.tools.registry import ToolRegistry
from agentkit.tools.router import ToolRouter


@tool(description="Echo back.")
async def echo(text: str) -> dict:
    return {"text": text}


@tool(description="Raise on demand.")
async def boom() -> dict:
    raise RuntimeError("planned failure")


def test_decorator_builds_executor():
    assert echo.spec.name == "echo"
    assert "text" in echo.spec.parameters["properties"]
    assert "text" in echo.spec.parameters["required"]


def test_registry_round_trip():
    reg = ToolRegistry([echo, boom])
    assert len(reg) == 2
    assert reg.has("echo")
    assert reg.get("echo").spec.name == "echo"
    with pytest.raises(ValueError):
        reg.register(echo)


async def test_router_dispatches_and_wraps_errors():
    reg = ToolRegistry([echo, boom])
    router = ToolRouter(reg)
    out = await router.dispatch(ToolCall(id="1", name="echo", arguments={"text": "hi"}))
    assert out == {"text": "hi"}

    with pytest.raises(ToolNotFound):
        await router.dispatch(ToolCall(id="2", name="missing"))

    with pytest.raises(ToolError):
        await router.dispatch(ToolCall(id="3", name="boom"))


async def test_harness_can_veto():
    async def deny(call):
        return HarnessVerdict(allowed=False, reason="nope")

    hook = make_hook(before=deny)
    harness = Harness([hook])
    router = ToolRouter(ToolRegistry([echo]), harness)
    with pytest.raises(HarnessRejected):
        await router.dispatch(ToolCall(id="1", name="echo", arguments={"text": "x"}))


def test_thread_fork_independent():
    t = Thread(system_prompt="be brief")
    t.add_user("hello")
    t.add_assistant(AssistantMessage(content="hi"))
    branch = t.fork()
    branch.add_user("second")
    assert len(t.messages) == 3
    assert len(branch.messages) == 4
    assert branch.id != t.id


def test_app_healthz_lists_tools():
    app = App(tools=ToolRegistry([echo, boom]))
    asgi = build_asgi(app)
    client = TestClient(asgi)
    resp = client.get("/healthz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert "echo" in body["tools"]
    assert "boom" in body["tools"]


def test_websocket_thread_started():
    app = App(tools=ToolRegistry([echo]))
    asgi = build_asgi(app)
    client = TestClient(asgi)
    with client.websocket_connect("/agent") as ws:
        evt = json.loads(ws.receive_text())
        assert evt["type"] == "thread_started"
        assert evt["thread_id"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
