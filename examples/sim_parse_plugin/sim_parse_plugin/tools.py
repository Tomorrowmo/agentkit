"""sim_parse tools — adapt simgraph parsers to the agent.

Real simgraph: `from simgraph.modules.ingest.parsers import OpenFOAMParser`.
Here: `_mock_parsers` for self-contained demo. Swap the import and the
rest is unchanged.
"""

from __future__ import annotations

import os

from agentkit.tools import tool

from sim_parse_plugin._mock_parsers import PARSERS, auto_detect


def _normalize(path: str) -> str:
    return os.path.abspath(os.path.normpath(path))


@tool(description="List supported solver formats and their file extensions.")
async def list_parsers() -> dict:
    return {
        "summary": f"{len(PARSERS)} parsers",
        "parsers": [
            {"name": name, "extensions": list(p.extensions)}
            for name, p in PARSERS.items()
        ],
    }


@tool(description="Detect which solver format owns the given path. Returns null if none matches.")
async def detect_format(path: str) -> dict:
    p = _normalize(path)
    if not os.path.exists(p):
        return {"error": f"path does not exist: {p}"}
    name = auto_detect(p)
    return {
        "summary": f"detected: {name}" if name else "no parser matches",
        "path": p,
        "format": name,
    }


@tool(description="Parse a path with whichever parser claims it. Errors if none match.")
async def auto_parse(path: str) -> dict:
    p = _normalize(path)
    if not os.path.exists(p):
        return {"error": f"path does not exist: {p}"}
    name = auto_detect(p)
    if name is None:
        return {"error": f"no parser matches: {p}"}
    parser = PARSERS[name]
    res = parser.parse(p)
    return {
        "summary": f"auto_parse[{name}] -> {len(res.files)} files",
        "solver": res.solver,
        "metadata": res.metadata,
        "file_count": len(res.files),
        "path": p,
    }


async def _force_parse(solver_key: str, path: str) -> dict:
    if solver_key not in PARSERS:
        return {"error": f"unknown solver: {solver_key}"}
    p = _normalize(path)
    if not os.path.exists(p):
        return {"error": f"path does not exist: {p}"}
    parser = PARSERS[solver_key]
    if not parser.detect(p):
        return {"error": f"{solver_key} parser does not recognize {p}"}
    res = parser.parse(p)
    return {
        "summary": f"parsed as {solver_key}",
        "solver": res.solver,
        "metadata": res.metadata,
        "file_count": len(res.files),
        "path": p,
    }


@tool(description="Force-parse a path as CGNS. Errors if the parser does not recognize it.")
async def parse_cgns(path: str) -> dict:
    return await _force_parse("CGNS", path)


@tool(description="Force-parse a path as OpenFOAM. Errors if structure is wrong.")
async def parse_openfoam(path: str) -> dict:
    return await _force_parse("OpenFOAM", path)


@tool(description="Force-parse a path as Fluent. Errors if the parser does not recognize it.")
async def parse_fluent(path: str) -> dict:
    return await _force_parse("Fluent", path)


SIM_PARSE_TOOLS = [list_parsers, detect_format, auto_parse, parse_cgns, parse_openfoam, parse_fluent]
