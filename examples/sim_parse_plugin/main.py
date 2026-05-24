"""sim_parse host — drives simgraph parsers as agent tools."""

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

from sim_parse_plugin import (
    SIM_PARSE_TOOLS,
    SimParseArtifactFactory,
    SimParsePromptBuilder,
    sim_parse_harness_hook,
)


def build_app() -> App:
    web_dir = HERE / "web"
    write_chat_ui(web_dir, title="sim_parse — solver format dispatcher")
    skills = SkillLoader(HERE / "sim_parse_plugin" / "skills").discover()
    return App(
        tools=ToolRegistry(SIM_PARSE_TOOLS),
        llm=LLMClient(model=os.environ.get("AGENTKIT_MODEL", "gpt-4o-mini")),
        harness=Harness([sim_parse_harness_hook]),
        prompt_builder=SimParsePromptBuilder(skills=skills),
        artifact_factory=SimParseArtifactFactory(),
        insight_log_path="./logs/sim_parse.jsonl",
        web_root=str(web_dir),
        web_title="sim_parse",
    )


def main() -> None:
    build_app().run(host="127.0.0.1", port=8769)


if __name__ == "__main__":
    main()
