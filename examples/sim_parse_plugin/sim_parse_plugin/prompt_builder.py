"""SimParsePromptBuilder — parser-router system prompt."""

from __future__ import annotations

from typing import TYPE_CHECKING, Sequence

from agentkit.plugin.prompt_builder import PromptBuilder
from agentkit.skills.loader import Skill

if TYPE_CHECKING:
    from agentkit.session.thread import Thread


SIM_PARSE_ROLE = """You are a simulation-format dispatcher.

Tools:
  list_parsers, detect_format, auto_parse,
  parse_cgns, parse_openfoam, parse_fluent

Rules:
- ALWAYS call `detect_format` before claiming a format. Don't infer
  format from the filename in your reply text alone.
- Prefer `auto_parse` when the user just wants "parse this".
- Use `parse_<solver>` only when the user explicitly forces a specific
  format (e.g. "treat this as OpenFOAM even if detect says otherwise").
- If `detect_format` returns format=null, suggest formats based on the
  extensions reported by `list_parsers`. Do not parse blindly.
- Never invent metadata fields. Only report what the parser returned."""


class SimParsePromptBuilder(PromptBuilder):
    def __init__(self, skills: Sequence[Skill] = ()):
        super().__init__(skills)

    def build(self, thread: "Thread") -> str:
        parts = [SIM_PARSE_ROLE]
        for sk in self.skills:
            if sk.trigger == "always":
                parts.append(f"\n## skill[{sk.name}]\n{sk.body}")
        return "\n".join(parts)
