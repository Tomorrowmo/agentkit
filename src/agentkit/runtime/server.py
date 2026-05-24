"""ASGI bootstrap.

Builds the FastAPI app, mounts the WebSocket router, and exposes a
trivial health endpoint. Hosts can add their own routes by reaching
into the returned FastAPI instance.

If the App was constructed with `web_root=<path-to-dir>`, that dir is
mounted at `/` as a static site (single-page chat UI per plugin).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from agentkit.ipc.websocket import build_router

if TYPE_CHECKING:
    from agentkit.plugin.app import App


def build_asgi(app: "App") -> FastAPI:
    fast = FastAPI(title="agentkit")

    @fast.get("/healthz")
    async def healthz() -> dict:
        return {
            "ok": True,
            "tools": [s.name for s in app.registry.all_specs()],
            "title": app.web_title,
        }

    @fast.get("/api/tools")
    async def list_tools() -> list:
        return [
            {"name": s.name, "description": s.description}
            for s in app.registry.all_specs()
        ]

    fast.include_router(build_router(app))

    web_root = getattr(app, "web_root", None)
    if web_root:
        root = Path(web_root)
        if root.exists():
            index = root / "index.html"

            @fast.get("/")
            async def _index():
                return FileResponse(str(index)) if index.exists() else {"ok": True}

            fast.mount("/static", StaticFiles(directory=str(root)), name="static")

    return fast
