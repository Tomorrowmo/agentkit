"""Test the multi-app composition primitives.

Important: this verifies that no plugin code had to change to coexist.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "chatcfd_plugin"))
sys.path.insert(0, str(HERE.parent / "simgraph_plugin"))
sys.path.insert(0, str(HERE))

import pytest

from agentkit.harness.base import Harness
from agentkit.protocol.messages import ToolCall
from agentkit.session.thread import Thread
from agentkit.tools.registry import ToolRegistry
from agentkit.tools.router import ToolRouter

from chatcfd_plugin import CFD_TOOLS, CFDArtifactFactory, CFDPromptBuilder, cfd_harness_hook
from simgraph_plugin import (
    SIMGRAPH_TOOLS,
    SimGraphArtifactFactory,
    SimGraphPromptBuilder,
    simgraph_harness_hook,
)

from main import UnionArtifactFactory, UnionPromptBuilder


def test_no_tool_name_collision():
    cfd = {t.spec.name for t in CFD_TOOLS}
    sg = {t.spec.name for t in SIMGRAPH_TOOLS}
    assert cfd.isdisjoint(sg), f"name collision: {cfd & sg}"


def test_merged_registry_has_all_12_tools():
    reg = ToolRegistry(list(CFD_TOOLS) + list(SIMGRAPH_TOOLS))
    assert len(reg) == 12


async def test_router_dispatches_either_app():
    reg = ToolRegistry(list(CFD_TOOLS) + list(SIMGRAPH_TOOLS))
    h = Harness([cfd_harness_hook, simgraph_harness_hook])
    router = ToolRouter(reg, h)
    cfd_out = await router.dispatch(ToolCall(id="1", name="listFiles"))
    sg_out = await router.dispatch(
        ToolCall(id="2", name="query_graph", arguments={"question": "Ma6"})
    )
    assert "data" in cfd_out
    assert "hits" in sg_out


def test_union_prompt_includes_both_roles():
    pb = UnionPromptBuilder([CFDPromptBuilder(), SimGraphPromptBuilder()])
    t = Thread()
    prompt = pb.build(t)
    assert "CFD post-processing assistant" in prompt
    assert "simulation-data librarian" in prompt
    assert "---" in prompt  # separator


def test_union_artifact_factory_first_match_wins():
    f = UnionArtifactFactory([CFDArtifactFactory(), SimGraphArtifactFactory()])
    # query_graph is only handled by SimGraphArtifactFactory
    a = f.make("query_graph", {"question": "x"}, {"summary": "1", "hits": []})
    assert a is not None
    assert a["kind"] == "result_list"

    # calculate is only handled by CFDArtifactFactory
    b = f.make("calculate", {"method": "force"}, {"summary": "x", "values": {"Fx": 1}})
    assert b["kind"] == "table"

    # unknown tool → None
    assert f.make("unknown_tool", {}, {}) is None


async def test_cross_app_workflow_simulation():
    """Manually simulate the LLM orchestration: simgraph query -> chatcfd load."""
    reg = ToolRegistry(list(CFD_TOOLS) + list(SIMGRAPH_TOOLS))
    router = ToolRouter(reg)

    # 1) Search the index
    hits = await router.dispatch(
        ToolCall(id="1", name="query_graph", arguments={"question": "张伟 Ma6"})
    )
    assert hits["hits"], "expected at least one hit"
    # 2) An LLM would map first hit's path to a case the chatcfd mocks know;
    #    for the demo we pick a known chatcfd case to show the chain works.
    loaded = await router.dispatch(
        ToolCall(id="2", name="loadFile", arguments={"case": "aero_2024_03_run023"})
    )
    sid = loaded["session_id"]
    # 3) Calculate forces in the same chain
    forces = await router.dispatch(
        ToolCall(
            id="3",
            name="calculate",
            arguments={"session_id": sid, "method": "force"},
        )
    )
    assert set(forces["values"]) == {"Fx", "Fy", "Fz"}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
