"""WebSocket transport.

Wire format — client → server:
    { "type": "user_message", "content": "...", "thread_id": "?" }
    { "type": "cancel" }                           (Phase 2)

Wire format — server → client:
    Each StreamEvent (events.py) serialized as JSON. Clients use the
    `type` field to discriminate.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

if TYPE_CHECKING:
    from agentkit.plugin.app import App


def build_router(app: "App") -> APIRouter:
    router = APIRouter()

    @router.websocket("/agent")
    async def agent_ws(ws: WebSocket) -> None:
        await ws.accept()
        thread = app.open_thread()
        await ws.send_text(_dump(app.started_event(thread)))
        try:
            while True:
                raw = await ws.receive_text()
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    await ws.send_text(json.dumps({"type": "error", "message": "invalid json"}))
                    continue
                if msg.get("type") != "user_message":
                    await ws.send_text(json.dumps({"type": "error", "message": "unsupported type"}))
                    continue
                content = msg.get("content") or ""
                async for event in app.turn(thread, content):
                    await ws.send_text(_dump(event))
        except WebSocketDisconnect:
            return

    return router


def _dump(event: Any) -> str:
    if isinstance(event, BaseModel):
        return event.model_dump_json()
    return json.dumps(event, ensure_ascii=False, default=str)
