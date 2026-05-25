"""Eval setup + App builder for chatcfd.

No setup hooks needed (cases don't seed state). Just the builder
function so `python -m agentkit.eval run ... --app chatcfd_plugin.eval_setup:build_eval_app`
works.
"""

from __future__ import annotations

from pathlib import Path

from agentkit import App
from agentkit.harness.base import Harness
from agentkit.llm.client import LLMClient
from agentkit.skills.loader import SkillLoader
from agentkit.tools.registry import ToolRegistry

from chatcfd_plugin import (
    CFD_TOOLS,
    CFDArtifactFactory,
    CFDMemoryHook,
    CFDPromptBuilder,
    cfd_harness_hook,
)


HERE = Path(__file__).parent.parent


def build_eval_app(llm: LLMClient) -> App:
    skills = SkillLoader(HERE / "chatcfd_plugin" / "skills").discover()
    return App(
        tools=ToolRegistry(CFD_TOOLS),
        llm=llm,
        harness=Harness([cfd_harness_hook]),
        prompt_builder=CFDPromptBuilder(skills=skills),
        artifact_factory=CFDArtifactFactory(),
        context_hooks=[CFDMemoryHook()],
    )
