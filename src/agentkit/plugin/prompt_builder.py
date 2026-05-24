"""PromptBuilder — host-supplied policy for building the system prompt.

Default implementation: concatenates the bodies of all loaded skills,
nothing else. CFD/SimGraph plugins override `build()` to weave in
business context (case files, role definitions, etc.) — that code does
NOT live in agentkit.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Sequence

from agentkit.skills.loader import Skill

if TYPE_CHECKING:
    from agentkit.session.thread import Thread


class PromptBuilder:
    def __init__(self, skills: Sequence[Skill] = ()):
        self.skills = list(skills)

    def build(self, thread: "Thread") -> str:  # noqa: ARG002
        parts: list[str] = []
        for sk in self.skills:
            if sk.trigger == "always":
                parts.append(sk.body)
        return "\n\n---\n\n".join(parts)
