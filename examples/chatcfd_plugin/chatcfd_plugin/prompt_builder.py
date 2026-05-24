"""CFDPromptBuilder — CFD-specific system prompt assembly.

This is the kind of code that should NEVER live in the framework. It
knows about cases, zones, units, the loaded-session concept. Framework
sees only `PromptBuilder.build(thread) -> str`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Sequence

from agentkit.plugin.prompt_builder import PromptBuilder
from agentkit.skills.loader import Skill

if TYPE_CHECKING:
    from agentkit.session.thread import Thread


@dataclass
class CFDState:
    """Tracked in Thread.metadata['cfd_state'] — updated by tools/hooks."""

    active_case: str | None = None
    loaded_sessions: list[str] = field(default_factory=list)


CFD_ROLE = """You are a CFD post-processing assistant.

You analyze incompressible/compressible flow simulations. Available tools:
- listFiles, loadFile, calculate, compare, exportData, getMethodTemplate

Workflow rules:
- Always loadFile before calculate/compare/exportData.
- For 'force' calculations, ask for the reference area if the user did not say.
- Quantities are in SI unless the user states otherwise.
- Be concise. The user sees tool results separately — do not repeat them verbatim."""


class CFDPromptBuilder(PromptBuilder):
    def __init__(self, skills: Sequence[Skill] = ()):
        super().__init__(skills)

    def build(self, thread: "Thread") -> str:
        state: CFDState = thread.metadata.get("cfd_state") or CFDState()

        parts: list[str] = [CFD_ROLE]

        if state.active_case:
            parts.append(f"\n## Active case\n- name: {state.active_case}")
        if state.loaded_sessions:
            parts.append(
                "\n## Loaded sessions\n"
                + "\n".join(f"- {s}" for s in state.loaded_sessions)
            )

        for sk in self.skills:
            if sk.trigger == "always":
                parts.append(f"\n## skill[{sk.name}]\n{sk.body}")

        return "\n".join(parts)
