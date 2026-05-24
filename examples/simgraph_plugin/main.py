"""simgraph reference host — assembles agentkit App from simgraph_plugin."""

from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from agentkit import App
from agentkit.harness.base import Harness
from agentkit.llm.client import LLMClient
from agentkit.session.compact import Compactor
from agentkit.skills.loader import SkillLoader
from agentkit.tools.registry import ToolRegistry

from simgraph_plugin import (
    SIMGRAPH_TOOLS,
    SimGraphArtifactFactory,
    SimGraphPromptBuilder,
    simgraph_harness_hook,
)


def build_app() -> App:
    skills = SkillLoader(HERE / "simgraph_plugin" / "skills").discover()
    llm = LLMClient(model=os.environ.get("AGENTKIT_MODEL", "gpt-4o-mini"))
    return App(
        tools=ToolRegistry(SIMGRAPH_TOOLS),
        llm=llm,
        harness=Harness([simgraph_harness_hook]),
        prompt_builder=SimGraphPromptBuilder(skills=skills),
        artifact_factory=SimGraphArtifactFactory(),
        compactor=Compactor(llm),  # long search sessions, opt-in to compression
        insight_log_path="./logs/simgraph.jsonl",
    )


def main() -> None:
    build_app().run(host="127.0.0.1", port=8766)


if __name__ == "__main__":
    main()
