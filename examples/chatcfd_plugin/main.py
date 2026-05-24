"""chatcfd reference host — assembles agentkit App from chatcfd_plugin pieces.

The whole "wire it up" stage is ~20 lines. Everything CFD-specific lives
in the chatcfd_plugin package; nothing in this file is framework code.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Let `python examples/chatcfd_plugin/main.py` work without installing the plugin.
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from agentkit import App
from agentkit.harness.base import Harness
from agentkit.llm.client import LLMClient
from agentkit.runtime import write_chat_ui
from agentkit.skills.loader import SkillLoader
from agentkit.tools.registry import ToolRegistry

from chatcfd_plugin import (
    CFD_TOOLS,
    CFDArtifactFactory,
    CFDMemoryHook,
    CFDPromptBuilder,
    cfd_harness_hook,
)


def build_app() -> App:
    web_dir = HERE / "web"
    write_chat_ui(web_dir, title="chatcfd — CFD analysis agent")
    skills = SkillLoader(HERE / "chatcfd_plugin" / "skills").discover()
    return App(
        tools=ToolRegistry(CFD_TOOLS),
        llm=LLMClient(model=os.environ.get("AGENTKIT_MODEL", "gpt-4o-mini")),
        harness=Harness([cfd_harness_hook]),
        prompt_builder=CFDPromptBuilder(skills=skills),
        artifact_factory=CFDArtifactFactory(),
        context_hooks=[CFDMemoryHook()],
        insight_log_path="./logs/chatcfd.jsonl",
        web_root=str(web_dir),
        web_title="chatcfd",
    )


def main() -> None:
    build_app().run(host="127.0.0.1", port=8765)


if __name__ == "__main__":
    main()
