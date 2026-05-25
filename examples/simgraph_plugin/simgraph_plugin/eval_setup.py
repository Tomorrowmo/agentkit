"""Eval App builder for simgraph."""

from __future__ import annotations

from pathlib import Path

from agentkit import App
from agentkit.harness.base import Harness
from agentkit.llm.client import LLMClient
from agentkit.skills.loader import SkillLoader
from agentkit.tools.registry import ToolRegistry

from simgraph_plugin import (
    SIMGRAPH_TOOLS,
    SimGraphArtifactFactory,
    SimGraphPromptBuilder,
    simgraph_harness_hook,
)


HERE = Path(__file__).parent.parent


def build_eval_app(llm: LLMClient) -> App:
    skills = SkillLoader(HERE / "simgraph_plugin" / "skills").discover()
    return App(
        tools=ToolRegistry(SIMGRAPH_TOOLS),
        llm=llm,
        harness=Harness([simgraph_harness_hook]),
        prompt_builder=SimGraphPromptBuilder(skills=skills),
        artifact_factory=SimGraphArtifactFactory(),
    )
