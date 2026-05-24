"""The six CFD tools — local mocks that match the real chatcfd MCP shape.

Real chatcfd does not write these here; it points `App(mcp_servers=[...])`
at its `post_service` MCP server. The wire shapes below mirror the real
tools' return contract:

    { "summary": str, "data": <opaque>, "output_files": [...] }

`data` is a key in BINARY_KEYS (see agentkit.plugin.app), so the
framework strips it before showing the LLM — but the ArtifactFactory
still sees the full payload.
"""

from __future__ import annotations

import hashlib
import os
import random
from pathlib import Path

from agentkit.tools import tool

# Pretend case directory — just so the demo has something to list.
DEMO_CASES = {
    "aero_2024_03_run023": {"zones": ["wing", "fuselage", "wake"], "cells": 1_240_000},
    "naca0012_aoa5": {"zones": ["airfoil", "farfield"], "cells": 320_000},
}

# In-memory "session state" so calculate/exportData see what loadFile loaded.
_SESSIONS: dict[str, dict] = {}


@tool(description="List available CFD cases on disk.")
async def listFiles() -> dict:
    items = [
        {"name": k, "zones": v["zones"], "cells": v["cells"]}
        for k, v in DEMO_CASES.items()
    ]
    return {"summary": f"Found {len(items)} cases.", "data": items}


@tool(description="Load a case into the active session. Returns mesh metadata.")
async def loadFile(case: str) -> dict:
    if case not in DEMO_CASES:
        return {"error": f"unknown case: {case}"}
    meta = DEMO_CASES[case]
    session_id = hashlib.md5(case.encode()).hexdigest()[:8]
    fake_mesh_bytes = bytes(random.randint(0, 255) for _ in range(2048))
    _SESSIONS[session_id] = {"case": case, "zones": meta["zones"]}
    return {
        "summary": f"Loaded {case}: {len(meta['zones'])} zones, {meta['cells']:,} cells.",
        "session_id": session_id,
        "zones": meta["zones"],
        "cells": meta["cells"],
        "data": fake_mesh_bytes,  # ← stripped from LLM, kept for ArtifactFactory
    }


@tool(description="Run a calculation (force, velocity_gradient, statistics) on the active session.")
async def calculate(session_id: str, method: str, zone: str | None = None) -> dict:
    if session_id not in _SESSIONS:
        return {"error": f"session not loaded: {session_id}"}
    methods = {
        "force": {"Fx": round(random.uniform(-10, 10), 3),
                  "Fy": round(random.uniform(-1, 1), 3),
                  "Fz": round(random.uniform(-50, 50), 3)},
        "statistics": {"min": -1.2, "max": 3.4, "mean": 0.5},
        "velocity_gradient": {"max_vorticity": 124.6, "max_qcriterion": 88.1},
    }
    if method not in methods:
        return {"error": f"unknown method: {method}; choose from {list(methods)}"}
    result = methods[method]
    return {
        "summary": f"calculate({method}, zone={zone or 'all'}) -> {result}",
        "values": result,
    }


@tool(description="Compare a metric across N sessions.")
async def compare(session_ids: list, metric: str) -> dict:
    if not all(s in _SESSIONS for s in session_ids):
        return {"error": "one or more sessions not loaded"}
    rows = [{"session_id": s, metric: round(random.uniform(0, 1), 3)} for s in session_ids]
    return {"summary": f"compared {metric} across {len(rows)} sessions", "rows": rows}


@tool(description="Export an artifact (csv/png/vtu) from the active session.")
async def exportData(session_id: str, kind: str = "csv") -> dict:
    if session_id not in _SESSIONS:
        return {"error": f"session not loaded: {session_id}"}
    case = _SESSIONS[session_id]["case"]
    path = f"./exports/{case}.{kind}"
    return {
        "summary": f"exported {kind} -> {path}",
        "output_files": [path],
    }


@tool(description="Fetch a template snippet describing how a given method is configured.")
async def getMethodTemplate(method: str) -> dict:
    templates = {
        "force": "Inputs: zone, ref_area, ref_velocity. Output: Fx/Fy/Fz, Cx/Cy/Cz.",
        "statistics": "Inputs: scalar_name. Output: min/max/mean/std.",
        "velocity_gradient": "Inputs: zone. Output: vorticity, q-criterion field.",
    }
    if method not in templates:
        return {"error": f"no template for: {method}"}
    return {"summary": f"template[{method}]", "template": templates[method]}


CFD_TOOLS = [listFiles, loadFile, calculate, compare, exportData, getMethodTemplate]


def case_root() -> Path:
    """Where the harness allows reads. Real chatcfd reads CHATCFD_CASE_ROOT env."""
    return Path(os.environ.get("CHATCFD_CASE_ROOT", "./cases")).resolve()
