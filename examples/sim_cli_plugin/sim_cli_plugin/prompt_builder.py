"""SimCliPromptBuilder — ops-oriented system prompt."""

from __future__ import annotations

from typing import TYPE_CHECKING, Sequence

from agentkit.plugin.prompt_builder import PromptBuilder
from agentkit.skills.loader import Skill

if TYPE_CHECKING:
    from agentkit.session.thread import Thread


SIM_CLI_ROLE = """You are a simgraph deployment operator.

You manage the simgraph CLI's background processes (collector, MCP server,
post-service) on this machine. Tools:

  start_collector / start_mcp / start_post_service
  stop_process(name)
  cli_status / cli_version / init_config

Rules:
- ALWAYS call `cli_status` before claiming a service is up or down.
- Don't start a process if `cli_status` already shows it running.
- If `cli_version` errors, the simgraph executable isn't on PATH — say so;
  don't pretend to start things.
- One tool per fact. Never invent process names or PIDs."""


class SimCliPromptBuilder(PromptBuilder):
    def __init__(self, skills: Sequence[Skill] = ()):
        super().__init__(skills)

    def build(self, thread: "Thread") -> str:
        parts = [SIM_CLI_ROLE]
        for sk in self.skills:
            if sk.trigger == "always":
                parts.append(f"\n## skill[{sk.name}]\n{sk.body}")
        return "\n".join(parts)
