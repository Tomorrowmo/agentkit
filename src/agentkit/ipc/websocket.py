"""WebSocket transport.

Wire format — client → server:
    { "type": "user_message", "content": "...", "thread_id": "?" }
    { "type": "cancel", "thread_id": "..." }
    { "type": "fork",   "thread_id": "..." }      → server replies new thread_started
    { "type": "open",   "thread_id": "..." }      → resume an existing thread

Wire format — server → client:
    Each StreamEvent (events.py) serialized as JSON.

Concurrency: turns are dispatched on background tasks so the connection
keeps receiving (especially `cancel`) while a turn streams.
"""

from __future__ import annotations

import asyncio
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

        send_lock = asyncio.Lock()
        active_task: asyncio.Task | None = None

        async def send(event: Any) -> None:
            async with send_lock:
                await ws.send_text(_dump(event))

        async def run_turn(content: str) -> None:
            try:
                async for event in app.turn(thread, content):
                    await send(event)
            except Exception as exc:  # noqa: BLE001
                await send({"type": "error", "message": f"turn crashed: {exc}"})

        try:
            while True:
                raw = await ws.receive_text()
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    await send({"type": "error", "message": "invalid json"})
                    continue

                kind = msg.get("type")

                if kind == "user_message":
                    requested_tid = msg.get("thread_id")
                    if requested_tid and requested_tid != thread.id:
                        existing = app.threads.get(requested_tid)
                        if existing is None:
                            await send({"type": "error", "message": f"unknown thread_id: {requested_tid}"})
                            continue
                        thread = existing
                        await send(app.started_event(thread))
                    if active_task is not None and not active_task.done():
                        await send({"type": "error", "message": "turn already in progress"})
                        continue
                    active_task = asyncio.create_task(run_turn(msg.get("content") or ""))

                elif kind == "cancel":
                    target = msg.get("thread_id") or thread.id
                    cancelled = app.cancel_turn(target)
                    await send({"type": "cancel_ack", "thread_id": target, "cancelled": cancelled})

                elif kind == "fork":
                    base_id = msg.get("thread_id") or thread.id
                    base = app.threads.get(base_id)
                    if base is None:
                        await send({"type": "error", "message": f"unknown thread_id: {base_id}"})
                        continue
                    new = base.fork()
                    app.threads.register(new)
                    thread = new
                    await send(app.started_event(thread))

                elif kind == "open":
                    target = msg.get("thread_id")
                    existing = app.threads.get(target) if target else None
                    if existing is None:
                        await send({"type": "error", "message": f"unknown thread_id: {target}"})
                        continue
                    thread = existing
                    await send(app.started_event(thread))

                else:
                    await send({"type": "error", "message": f"unsupported type: {kind}"})
        except WebSocketDisconnect:
            if active_task is not None and not active_task.done():
                active_task.cancel()
            return

    return router


def _dump(event: Any) -> str:
    if isinstance(event, BaseModel):
        return event.model_dump_json()
    return json.dumps(event, ensure_ascii=False, default=str)
