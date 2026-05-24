"""ThreadPool — in-memory thread store.

Deliberately simple. If a host needs persistence across restarts,
subclass and override the four methods. Backend interface stays small
on purpose.
"""

from __future__ import annotations

from typing import Iterable

from agentkit.session.thread import Thread


class ThreadPool:
    def __init__(self) -> None:
        self._threads: dict[str, Thread] = {}

    def create(self, system_prompt: str | None = None) -> Thread:
        t = Thread(system_prompt=system_prompt)
        self._threads[t.id] = t
        return t

    def get(self, thread_id: str) -> Thread | None:
        return self._threads.get(thread_id)

    def register(self, thread: Thread) -> None:
        """Insert an externally-built thread (e.g. result of fork())."""
        self._threads[thread.id] = thread

    def get_or_create(self, thread_id: str | None, system_prompt: str | None = None) -> Thread:
        if thread_id and thread_id in self._threads:
            return self._threads[thread_id]
        t = Thread(thread_id=thread_id, system_prompt=system_prompt)
        self._threads[t.id] = t
        return t

    def remove(self, thread_id: str) -> None:
        self._threads.pop(thread_id, None)

    def list(self) -> Iterable[Thread]:
        return self._threads.values()
