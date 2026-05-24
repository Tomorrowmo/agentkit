"""Offline test for chatcfd_plugin — no LLM key required.

Exercises:
  - Local tools dispatch through ToolRouter
  - CFDPromptBuilder picks up state + skills
  - CFDArtifactFactory builds mesh / table / file artifacts
  - cfd_harness_hook rejects out-of-root paths
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

import pytest

from agentkit.harness.base import Harness
from agentkit.plugin.app import _strip_binary
from agentkit.protocol.errors import HarnessRejected
from agentkit.protocol.messages import ToolCall
from agentkit.session.thread import Thread
from agentkit.skills.loader import SkillLoader
from agentkit.tools.registry import ToolRegistry
from agentkit.tools.router import ToolRouter

from chatcfd_plugin import (
    CFD_TOOLS,
    CFDArtifactFactory,
    CFDPromptBuilder,
    CFDState,
    cfd_harness_hook,
)


@pytest.fixture
def router():
    return ToolRouter(ToolRegistry(CFD_TOOLS), Harness([cfd_harness_hook]))


async def test_listfiles_returns_demo_cases(router):
    out = await router.dispatch(ToolCall(id="1", name="listFiles"))
    assert "aero_2024_03_run023" in {r["name"] for r in out["data"]}


async def test_loadfile_strips_mesh_for_llm(router):
    raw = await router.dispatch(
        ToolCall(id="1", name="loadFile", arguments={"case": "naca0012_aoa5"})
    )
    assert isinstance(raw["data"], (bytes, bytearray))

    llm_view = _strip_binary(raw)
    assert llm_view["data"] == {"_stripped": True, "kind": "bytes", "approx_size": 2048}
    assert "session_id" in llm_view
    assert raw["zones"] == llm_view["zones"]


async def test_loadfile_then_calculate(router):
    loaded = await router.dispatch(
        ToolCall(id="1", name="loadFile", arguments={"case": "naca0012_aoa5"})
    )
    sid = loaded["session_id"]
    forces = await router.dispatch(
        ToolCall(
            id="2",
            name="calculate",
            arguments={"session_id": sid, "method": "force", "zone": "airfoil"},
        )
    )
    assert set(forces["values"]) == {"Fx", "Fy", "Fz"}


async def test_calculate_before_loadfile_returns_error(router):
    out = await router.dispatch(
        ToolCall(
            id="1",
            name="calculate",
            arguments={"session_id": "deadbeef", "method": "force"},
        )
    )
    assert "error" in out


async def test_harness_rejects_path_outside_case_root(router):
    with pytest.raises(HarnessRejected):
        await router.dispatch(
            ToolCall(
                id="1",
                name="loadFile",
                arguments={"case": "/etc/passwd"},
            )
        )


def test_prompt_includes_active_case_and_skills():
    skills = SkillLoader(HERE / "chatcfd_plugin" / "skills").discover()
    pb = CFDPromptBuilder(skills=skills)
    t = Thread()
    t.metadata["cfd_state"] = CFDState(active_case="naca0012_aoa5")
    prompt = pb.build(t)
    assert "naca0012_aoa5" in prompt
    assert "loadFile" in prompt
    assert "skill[cfd-loadfile]" in prompt
    assert "SI" in prompt  # from cfd-units skill


def test_artifact_factory_mesh_kind():
    f = CFDArtifactFactory()
    a = f.make(
        "loadFile",
        {"case": "naca0012_aoa5"},
        {
            "summary": "Loaded",
            "session_id": "x",
            "zones": ["airfoil"],
            "cells": 100,
            "data": b"\x00\x01\x02",
        },
    )
    assert a["kind"] == "mesh"
    assert len(a["mesh_hash"]) == 12


def test_artifact_factory_table_kind():
    f = CFDArtifactFactory()
    a = f.make(
        "calculate",
        {"method": "force"},
        {"summary": "x", "values": {"Fx": 1.0}},
    )
    assert a["kind"] == "table"


def test_artifact_factory_returns_none_for_errors():
    f = CFDArtifactFactory()
    assert f.make("loadFile", {"case": "x"}, {"error": "boom"}) is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
