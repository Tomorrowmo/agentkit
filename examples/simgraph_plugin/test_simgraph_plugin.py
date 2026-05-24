"""Offline test for simgraph_plugin — no LLM key required."""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

import pytest

from agentkit.harness.base import Harness
from agentkit.protocol.messages import ToolCall
from agentkit.session.thread import Thread
from agentkit.skills.loader import SkillLoader
from agentkit.tools.registry import ToolRegistry
from agentkit.tools.router import ToolRouter

from simgraph_plugin import (
    SIMGRAPH_TOOLS,
    SimGraphArtifactFactory,
    SimGraphPromptBuilder,
    SimGraphState,
    simgraph_harness_hook,
)


@pytest.fixture
def router():
    return ToolRouter(ToolRegistry(SIMGRAPH_TOOLS), Harness([simgraph_harness_hook]))


async def test_query_returns_zhang_wei_converged(router):
    out = await router.dispatch(
        ToolCall(id="1", name="query_graph", arguments={"question": "张伟 已收敛 Ma6"})
    )
    assert out["hits"]
    assert all(h["owner"] == "张伟" for h in out["hits"])
    assert all(h["converged"] for h in out["hits"])


async def test_get_card(router):
    out = await router.dispatch(
        ToolCall(id="1", name="get_card", arguments={"file_id": "f001"})
    )
    assert out["card"]["owner"] == "张伟"


async def test_find_similar_prefers_same_project(router):
    out = await router.dispatch(
        ToolCall(id="1", name="find_similar", arguments={"file_id": "f001", "k": 2})
    )
    top = out["neighbors"][0]
    assert top["file_id"] == "f002"  # same project + close Ma


async def test_trace_provenance(router):
    out = await router.dispatch(
        ToolCall(id="1", name="trace_provenance", arguments={"file_id": "f001"})
    )
    assert "mesh_v3" in out["upstream"]


def test_prompt_includes_pinned_and_recent():
    skills = SkillLoader(HERE / "simgraph_plugin" / "skills").discover()
    pb = SimGraphPromptBuilder(skills=skills)
    t = Thread()
    t.metadata["sg_state"] = SimGraphState(
        pinned_files=["f001", "f003"],
        recent_queries=["张伟做的Ma6", "未收敛的算例"],
    )
    prompt = pb.build(t)
    assert "f001" in prompt
    assert "未收敛的算例" in prompt
    assert "query_graph" in prompt
    assert "skill[simgraph-search]" in prompt


def test_artifact_factory_result_list():
    f = SimGraphArtifactFactory()
    a = f.make("query_graph", {"question": "x"}, {"summary": "1", "hits": [{"file_id": "f001"}]})
    assert a["kind"] == "result_list"


def test_artifact_factory_subgraph():
    f = SimGraphArtifactFactory()
    a = f.make("trace_provenance", {"file_id": "f001"},
               {"summary": "x", "file_id": "f001", "upstream": ["mesh_v3"]})
    assert a["kind"] == "subgraph"
    assert ("mesh_v3", "f001", "PRODUCES") in a["edges"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
