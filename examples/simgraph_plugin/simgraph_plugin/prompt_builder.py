"""SimGraphPromptBuilder — graph-search-oriented system prompt.

Contrast with CFDPromptBuilder: that one tracks an active session;
this one tracks recent search history and pinned files. Both subclass
the same PromptBuilder ABC and override `build(thread) -> str`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Sequence

from agentkit.plugin.prompt_builder import PromptBuilder
from agentkit.skills.loader import Skill

if TYPE_CHECKING:
    from agentkit.session.thread import Thread


@dataclass
class SimGraphState:
    pinned_files: list[str] = field(default_factory=list)
    recent_queries: list[str] = field(default_factory=list)


SIMGRAPH_ROLE = """You are a simulation-data librarian.

Users ask you to find historical simulation cases in a Neo4j-backed index.
Available tools: ingest_file, extract_metadata, query_graph, get_card,
find_similar, trace_provenance.

Rules:
- For "find X" / "search Y", call query_graph first.
- When confidence is LOW or MED, surface it to the user.
- Always cite the file_id you used so the user can pin it.
- Don't make up params — if confidence is missing, say so."""


class SimGraphPromptBuilder(PromptBuilder):
    def __init__(self, skills: Sequence[Skill] = ()):
        super().__init__(skills)

    def build(self, thread: "Thread") -> str:
        state: SimGraphState = thread.metadata.get("sg_state") or SimGraphState()

        parts: list[str] = [SIMGRAPH_ROLE]

        if state.pinned_files:
            parts.append(
                "\n## Pinned files\n"
                + "\n".join(f"- {f}" for f in state.pinned_files)
            )
        if state.recent_queries:
            parts.append(
                "\n## Recent queries\n"
                + "\n".join(f"- {q}" for q in state.recent_queries[-5:])
            )

        for sk in self.skills:
            if sk.trigger == "always":
                parts.append(f"\n## skill[{sk.name}]\n{sk.body}")

        return "\n".join(parts)
