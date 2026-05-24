"""TurnContext — per-turn scratch space.

A Turn is one full cycle: user message → LLM round-trips (incl. tool
calls) → final assistant message. Per-turn cancel tokens and "events
queued this turn" live here so they don't leak into the next turn.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field

from agentkit.session.thread import Thread


@dataclass
class TurnContext:
    thread: Thread
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)

    def cancel(self) -> None:
        self.cancel_event.set()

    @property
    def cancelled(self) -> bool:
        return self.cancel_event.is_set()
