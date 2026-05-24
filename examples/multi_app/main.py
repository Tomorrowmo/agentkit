"""multi_app — chatcfd + simgraph in one agentkit host.

The composition primitives (UnionPromptBuilder, UnionArtifactFactory)
are defined here, in HOST land, not in agentkit. The framework already
supports composing tools (one registry) and harness hooks (one list);
prompts and artifacts compose by trivial wrappers.

This file is the entire integration: ~60 lines.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Sequence

HERE = Path(__file__).parent
CHATCFD_PLUGIN = HERE.parent / "chatcfd_plugin"
SIMGRAPH_PLUGIN = HERE.parent / "simgraph_plugin"
sys.path.insert(0, str(CHATCFD_PLUGIN))
sys.path.insert(0, str(SIMGRAPH_PLUGIN))

from agentkit import App
from agentkit.harness.base import Harness
from agentkit.llm.client import LLMClient
from agentkit.plugin.artifact_factory import ArtifactFactory
from agentkit.plugin.prompt_builder import PromptBuilder
from agentkit.session.compact import Compactor
from agentkit.skills.loader import SkillLoader
from agentkit.tools.registry import ToolRegistry

from chatcfd_plugin import (
    CFD_TOOLS,
    CFDArtifactFactory,
    CFDMemoryHook,
    CFDPromptBuilder,
    cfd_harness_hook,
)
from simgraph_plugin import (
    SIMGRAPH_TOOLS,
    SimGraphArtifactFactory,
    SimGraphPromptBuilder,
    simgraph_harness_hook,
)


class UnionPromptBuilder(PromptBuilder):
    """Concatenate multiple PromptBuilder outputs with a separator."""

    def __init__(self, builders: Sequence[PromptBuilder]):
        super().__init__()
        self.builders = list(builders)

    def build(self, thread) -> str:
        return "\n\n---\n\n".join(b.build(thread) for b in self.builders)


class UnionArtifactFactory(ArtifactFactory):
    """First non-None artifact wins. Order matters."""

    def __init__(self, factories: Sequence[ArtifactFactory]):
        self.factories = list(factories)

    def make(self, tool_name: str, arguments: dict[str, Any], result: Any):
        for f in self.factories:
            a = f.make(tool_name, arguments, result)
            if a is not None:
                return a
        return None


def build_app() -> App:
    cfd_skills = SkillLoader(CHATCFD_PLUGIN / "chatcfd_plugin" / "skills").discover()
    sg_skills = SkillLoader(SIMGRAPH_PLUGIN / "simgraph_plugin" / "skills").discover()
    llm = LLMClient(model=os.environ.get("AGENTKIT_MODEL", "gpt-4o-mini"))

    return App(
        # Tools: merge. ToolRegistry will raise on name collision —
        # both plugins use distinct naming conventions so they coexist.
        tools=ToolRegistry(list(CFD_TOOLS) + list(SIMGRAPH_TOOLS)),
        llm=llm,
        # Harness: native list — no wrapper needed.
        harness=Harness([cfd_harness_hook, simgraph_harness_hook]),
        # Prompt + artifact: trivial host-side composition.
        prompt_builder=UnionPromptBuilder(
            [
                CFDPromptBuilder(skills=cfd_skills),
                SimGraphPromptBuilder(skills=sg_skills),
            ]
        ),
        artifact_factory=UnionArtifactFactory(
            [CFDArtifactFactory(), SimGraphArtifactFactory()]
        ),
        context_hooks=[CFDMemoryHook()],
        compactor=Compactor(llm),
        insight_log_path="./logs/multi.jsonl",
    )


def main() -> None:
    build_app().run(host="127.0.0.1", port=8767)


if __name__ == "__main__":
    main()
