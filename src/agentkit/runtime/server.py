"""ASGI bootstrap.

Builds the FastAPI app, mounts the WebSocket router, and exposes a
trivial health endpoint. Hosts can add their own routes by reaching
into the returned FastAPI instance.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import FastAPI

from agentkit.ipc.websocket import build_router

if TYPE_CHECKING:
    from agentkit.plugin.app import App


def build_asgi(app: "App") -> FastAPI:
    fast = FastAPI(title="agentkit")

    @fast.get("/healthz")
    async def healthz() -> dict:
        return {"ok": True, "tools": [s.name for s in app.registry.all_specs()]}

    fast.include_router(build_router(app))
    return fast
