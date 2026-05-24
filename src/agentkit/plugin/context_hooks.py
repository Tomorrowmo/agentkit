"""ContextHook — host-supplied side-effects on turn boundaries.

Two hooks:
  before_turn(thread, user_message) — can rewrite the user message or
                                       mutate the thread (e.g. inject
                                       memory recall).
  after_turn(thread)                — can post-process the finished
                                       turn (e.g. extract facts to
                                       memory).

Both are async. Both return nothing — they mutate the thread in place
if needed.
"""

from __future__ import annotations

from agentkit.session.thread import Thread


class ContextHook:
    async def before_turn(self, thread: Thread, user_message: str) -> None:  # noqa: ARG002
        return None

    async def after_turn(self, thread: Thread) -> None:  # noqa: ARG002
        return None
