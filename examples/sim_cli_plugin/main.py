"""sim_cli host — drives simgraph CLI as agent tools."""

from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from agentkit import App
from agentkit.harness.base import Harness
from agentkit.llm.client import LLMClient
from agentkit.runtime import write_chat_ui
from agentkit.skills.loader import SkillLoader
from agentkit.tools.registry import ToolRegistry

from sim_cli_plugin import (
    SIM_CLI_TOOLS,
    SimCliArtifactFactory,
    SimCliPromptBuilder,
    simgraph_cli_harness_hook,
)


def build_app() -> App:
    web_dir = HERE / "web"
    write_chat_ui(web_dir, title="sim_cli — simgraph CLI driver")
    skills = SkillLoader(HERE / "sim_cli_plugin" / "skills").discover()
    return App(
        tools=ToolRegistry(SIM_CLI_TOOLS),
        llm=LLMClient(model=os.environ.get("AGENTKIT_MODEL", "gpt-4o-mini")),
        harness=Harness([simgraph_cli_harness_hook]),
        prompt_builder=SimCliPromptBuilder(skills=skills),
        artifact_factory=SimCliArtifactFactory(),
        insight_log_path="./logs/sim_cli.jsonl",
        web_root=str(web_dir),
        web_title="sim_cli",
    )


def main() -> None:
    build_app().run(host="127.0.0.1", port=8768)


if __name__ == "__main__":
    main()
