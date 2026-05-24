"""M3 tests: Compact + thread routing/cancel/fork in IPC."""

from __future__ import annotations

import json
from typing import Sequence

import pytest
from fastapi.testclient import TestClient

from agentkit import App, tool
from agentkit.llm.client import LLMClient, LLMResponse
from agentkit.protocol.messages import AssistantMessage, Message
from agentkit.protocol.tool_spec import ToolSpec
from agentkit.runtime.server import build_asgi
from agentkit.session.compact import CompactConfig, Compactor, estimate_tokens
from agentkit.session.thread import Thread
from agentkit.tools.registry import ToolRegistry


class FakeLLM(LLMClient):
    """Returns canned responses; counts how many times complete() ran."""

    def __init__(self, replies: list[str]):
        super().__init__(model="fake")
        self.replies = list(replies)
        self.calls = 0

    async def complete(self, messages: Sequence[Message], tools=None) -> LLMResponse:  # type: ignore[override]
        self.calls += 1
        text = self.replies.pop(0) if self.replies else "ok"
        return LLMResponse(message=AssistantMessage(content=text), finish_reason="stop")


def _padding(n_chars: int) -> str:
    return "x " * (n_chars // 2)


def test_estimate_tokens_scales_with_content():
    t = Thread()
    t.add_user(_padding(40))
    base = estimate_tokens(t.messages)
    t.add_user(_padding(40))
    assert estimate_tokens(t.messages) > base


async def test_compactor_skips_when_under_target():
    llm = FakeLLM(replies=["SUMMARY"])
    cmp = Compactor(llm, CompactConfig(target_tokens=10_000, keep_recent_turns=2))
    t = Thread()
    for _ in range(3):
        t.add_user("short")
        t.add_assistant(AssistantMessage(content="ok"))
    ran = await cmp.maybe_compact(t)
    assert ran is False
    assert llm.calls == 0


async def test_compactor_compresses_when_over_target():
    llm = FakeLLM(replies=["EARLIER: user picked case A then ran force calc"])
    cmp = Compactor(llm, CompactConfig(target_tokens=200, keep_recent_turns=2, chars_per_token=4))

    t = Thread(system_prompt="be brief")
    for i in range(8):
        t.add_user(_padding(200) + f" turn {i}")
        t.add_assistant(AssistantMessage(content=_padding(200) + f" reply {i}"))

    before_msgs = len(t.messages)
    ran = await cmp.maybe_compact(t)
    assert ran is True
    assert llm.calls == 1
    # System prompt kept + summary inserted + recent turns
    assert "[Earlier conversation summary]" in t.messages[1].content
    assert len(t.messages) < before_msgs


def test_thread_pool_register():
    app = App(tools=ToolRegistry())
    base = app.open_thread()
    forked = base.fork()
    assert app.threads.get(forked.id) is None
    app.threads.register(forked)
    assert app.threads.get(forked.id) is forked


def test_websocket_fork_creates_independent_thread():
    @tool(description="echo")
    async def echo(text: str) -> dict:
        return {"text": text}

    app = App(tools=ToolRegistry([echo]))
    client = TestClient(build_asgi(app))
    with client.websocket_connect("/agent") as ws:
        first = json.loads(ws.receive_text())
        original_tid = first["thread_id"]

        ws.send_text(json.dumps({"type": "fork", "thread_id": original_tid}))
        second = json.loads(ws.receive_text())
        assert second["type"] == "thread_started"
        assert second["thread_id"] != original_tid


def test_websocket_open_unknown_thread_returns_error():
    app = App(tools=ToolRegistry())
    client = TestClient(build_asgi(app))
    with client.websocket_connect("/agent") as ws:
        ws.receive_text()  # initial thread_started
        ws.send_text(json.dumps({"type": "open", "thread_id": "ghost"}))
        evt = json.loads(ws.receive_text())
        assert evt["type"] == "error"
        assert "unknown" in evt["message"]


def test_websocket_cancel_no_active_returns_false():
    app = App(tools=ToolRegistry())
    client = TestClient(build_asgi(app))
    with client.websocket_connect("/agent") as ws:
        first = json.loads(ws.receive_text())
        ws.send_text(json.dumps({"type": "cancel", "thread_id": first["thread_id"]}))
        evt = json.loads(ws.receive_text())
        assert evt["type"] == "cancel_ack"
        assert evt["cancelled"] is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
