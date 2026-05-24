"""SimGraph tools — mocked Neo4j + LLM-extracted metadata.

Real simgraph would have these as MCP tools served from `backend/` or
local Python proxies wrapping Neo4j + the LLM extractor. The mock
keeps the demo self-contained but mirrors the wire shape.

Notice the contrast with chatcfd's tools:
  - chatcfd has session_id state (loadFile → calculate chain)
  - simgraph is mostly stateless graph queries
  - chatcfd returns mesh blobs (binary); simgraph returns data cards
"""

from __future__ import annotations

import os
from pathlib import Path

from agentkit.tools import tool

# Fake "graph" — a flat dict keyed by file_id.
_GRAPH: dict[str, dict] = {
    "f001": {
        "path": "/shared/aero/2024_03/case_run023/",
        "owner": "张伟",
        "project": "XX-1",
        "Ma": 6.0,
        "AoA": 4.0,
        "converged": True,
        "convergence_confidence": "HIGH",
        "params_confidence": "MED",
        "upstream": ["mesh_v3", "setup_doc_v2"],
    },
    "f002": {
        "path": "/shared/aero/2024_03/case_run024/",
        "owner": "张伟",
        "project": "XX-1",
        "Ma": 6.2,
        "AoA": 5.0,
        "converged": False,
        "convergence_confidence": "HIGH",
        "params_confidence": "MED",
        "upstream": ["mesh_v3", "setup_doc_v2"],
    },
    "f003": {
        "path": "/shared/aero/2024_05/case_run041/",
        "owner": "李雯",
        "project": "XX-2",
        "Ma": 2.5,
        "AoA": 0.0,
        "converged": True,
        "convergence_confidence": "HIGH",
        "params_confidence": "HIGH",
        "upstream": ["mesh_v4"],
    },
}


@tool(description="Ingest a simulation file path into the graph. Returns file_id.")
async def ingest_file(path: str) -> dict:
    file_id = f"f{(hash(path) & 0xFFF):03x}"
    if file_id in _GRAPH:
        return {"summary": f"already ingested as {file_id}", "file_id": file_id}
    _GRAPH[file_id] = {"path": path, "owner": "(pending)", "project": "(pending)"}
    return {"summary": f"queued for extraction: {file_id}", "file_id": file_id}


@tool(description="Run LLM-based metadata extraction on a previously-ingested file.")
async def extract_metadata(file_id: str) -> dict:
    if file_id not in _GRAPH:
        return {"error": f"unknown file_id: {file_id}"}
    card = _GRAPH[file_id]
    return {
        "summary": f"metadata for {file_id}",
        "file_id": file_id,
        "params": {k: card.get(k) for k in ("Ma", "AoA", "converged")},
        "confidence": {
            "params": card.get("params_confidence", "LOW"),
            "convergence": card.get("convergence_confidence", "LOW"),
        },
    }


@tool(description="Natural-language search over the graph. Returns matching file cards.")
async def query_graph(question: str) -> dict:
    q = question.lower()
    hits = []
    for fid, card in _GRAPH.items():
        ok = True
        if "已收敛" in q or "converged" in q:
            ok = ok and card.get("converged", False)
        if "未收敛" in q or "not converged" in q:
            ok = ok and not card.get("converged", True)
        if "ma6" in q or "ma=6" in q or "ma 6" in q:
            ok = ok and abs(card.get("Ma", 0) - 6.0) < 0.5
        if "张伟" in q:
            ok = ok and card.get("owner") == "张伟"
        if ok:
            hits.append({"file_id": fid, **card})
    return {"summary": f"{len(hits)} match(es)", "hits": hits[:10]}


@tool(description="Fetch the full data card for one file_id.")
async def get_card(file_id: str) -> dict:
    if file_id not in _GRAPH:
        return {"error": f"unknown file_id: {file_id}"}
    return {"summary": f"card[{file_id}]", "card": _GRAPH[file_id]}


@tool(description="Find files similar to the given one (same project / nearby Ma).")
async def find_similar(file_id: str, k: int = 5) -> dict:
    if file_id not in _GRAPH:
        return {"error": f"unknown file_id: {file_id}"}
    base = _GRAPH[file_id]
    base_Ma = base.get("Ma", 0)
    base_proj = base.get("project")
    scored = []
    for fid, card in _GRAPH.items():
        if fid == file_id:
            continue
        score = 0
        if card.get("project") == base_proj:
            score += 2
        score += max(0, 5 - abs(card.get("Ma", 0) - base_Ma))
        scored.append((score, fid, card))
    scored.sort(reverse=True)
    return {
        "summary": f"top {k} similar to {file_id}",
        "neighbors": [{"file_id": f, "score": round(s, 2), **c} for s, f, c in scored[:k]],
    }


@tool(description="Show the upstream provenance (mesh, setup docs) of a file.")
async def trace_provenance(file_id: str) -> dict:
    if file_id not in _GRAPH:
        return {"error": f"unknown file_id: {file_id}"}
    return {
        "summary": f"provenance of {file_id}",
        "file_id": file_id,
        "upstream": _GRAPH[file_id].get("upstream", []),
    }


SIMGRAPH_TOOLS = [ingest_file, extract_metadata, query_graph, get_card, find_similar, trace_provenance]


def index_root() -> Path:
    return Path(os.environ.get("SIMGRAPH_INDEX_ROOT", "/shared")).resolve()
