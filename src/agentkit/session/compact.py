"""LLM-based history compression.

The problem: long threads (50+ turns of CFD analysis) blow context.
Naive sliding window throws away important early decisions; LLM-based
compression summarizes them and lets the rest fit.

Algorithm:
  1. If token count (estimated) under `target_tokens`, do nothing.
  2. Identify the head segment to compress: keep system + last
     `keep_recent` turns; compress the rest.
  3. Ask the LLM to produce a short structured summary of the head.
  4. Replace head with one SystemMessage carrying the summary.

Hosts can override the summary prompt and the trigger heuristic by
subclassing `Compactor`. Default is opinionated but small.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from agentkit.protocol.messages import (
    AssistantMessage,
    Message,
    SystemMessage,
    ToolMessage,
    UserMessage,
)

if TYPE_CHECKING:
    from agentkit.llm.client import LLMClient
    from agentkit.session.thread import Thread


SUMMARY_PROMPT = """You are summarizing an agent conversation so the head of \
the history can be replaced with one compact note. Produce a short summary \
covering:
- Decisions and conclusions the user agreed to
- Files / cases / objects the user is working with
- Open questions or pending work
Do NOT repeat tool outputs verbatim. ~150 words max. Plain text."""


@dataclass
class CompactConfig:
    target_tokens: int = 8000          # below this, no compression
    keep_recent_turns: int = 6         # how many turns (user+assistant pairs) to keep raw
    chars_per_token: int = 4           # crude estimator; works across providers


def estimate_tokens(messages: list[Message], chars_per_token: int = 4) -> int:
    chars = 0
    for m in messages:
        if isinstance(m, (SystemMessage, UserMessage)):
            chars += len(m.content or "")
        elif isinstance(m, AssistantMessage):
            chars += len(m.content or "")
            for tc in m.tool_calls:
                chars += len(tc.name) + len(str(tc.arguments))
        elif isinstance(m, ToolMessage):
            chars += len(m.content or "")
    return chars // chars_per_token


def _turn_boundaries(messages: list[Message]) -> list[int]:
    """Return indices of UserMessage occurrences — each starts a turn."""
    return [i for i, m in enumerate(messages) if isinstance(m, UserMessage)]


class Compactor:
    def __init__(self, llm: "LLMClient", config: CompactConfig | None = None):
        self.llm = llm
        self.config = config or CompactConfig()

    async def maybe_compact(self, thread: "Thread") -> bool:
        """Compress in place if needed. Returns True if it ran."""
        msgs = thread.messages
        if estimate_tokens(msgs, self.config.chars_per_token) < self.config.target_tokens:
            return False
        boundaries = _turn_boundaries(msgs)
        if len(boundaries) <= self.config.keep_recent_turns:
            return False
        head_end = boundaries[-self.config.keep_recent_turns]
        head_start = 1 if isinstance(msgs[0], SystemMessage) else 0
        head = msgs[head_start:head_end]
        if not head:
            return False
        summary = await self._summarize(head)
        note = SystemMessage(
            content=f"[Earlier conversation summary]\n{summary}"
        )
        # Splice: keep [0:head_start] + [note] + [head_end:]
        thread.messages = msgs[:head_start] + [note] + msgs[head_end:]
        return True

    async def _summarize(self, head: list[Message]) -> str:
        # Build a user-role message that asks for the summary. We deliberately
        # do NOT include real system or tool_calls in this sub-conversation —
        # just a flattened text rendering.
        transcript = _flatten(head)
        sub_msgs: list[Message] = [
            SystemMessage(content=SUMMARY_PROMPT),
            UserMessage(content=transcript),
        ]
        resp = await self.llm.complete(sub_msgs)
        return (resp.message.content or "").strip() or "(no summary produced)"


def _flatten(messages: list[Message]) -> str:
    lines: list[str] = []
    for m in messages:
        if isinstance(m, UserMessage):
            lines.append(f"USER: {m.content}")
        elif isinstance(m, AssistantMessage):
            if m.content:
                lines.append(f"ASSISTANT: {m.content}")
            for tc in m.tool_calls:
                lines.append(f"  -> tool[{tc.name}]({tc.arguments})")
        elif isinstance(m, ToolMessage):
            text = m.content or ""
            if len(text) > 400:
                text = text[:400] + "...[truncated]"
            lines.append(f"  <- tool_result[{m.name}]: {text}")
        elif isinstance(m, SystemMessage):
            continue  # system was already replaced upstream; skip
    return "\n".join(lines)
