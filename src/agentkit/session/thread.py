"""Thread — a conversation, first-class.

A thread owns the message list, an optional system prompt, and metadata.
Fork = deep copy of messages so the branch can diverge. Resume = pick
an existing thread by id.

No storage backend yet. ThreadPool keeps them in memory. Adding SQLite
or Redis later means making ThreadPool an interface — the Thread itself
stays simple.
"""

from __future__ import annotations

import copy
import time
import uuid
from typing import Any

from agentkit.protocol.messages import (
    AssistantMessage,
    Message,
    SystemMessage,
    ToolMessage,
    UserMessage,
)


class Thread:
    def __init__(
        self,
        thread_id: str | None = None,
        system_prompt: str | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        self.id = thread_id or uuid.uuid4().hex
        self.created_at = time.time()
        self.metadata: dict[str, Any] = metadata or {}
        self.messages: list[Message] = []
        if system_prompt:
            self.messages.append(SystemMessage(content=system_prompt))

    def set_system(self, prompt: str) -> None:
        """Replace or insert the system message."""
        if self.messages and isinstance(self.messages[0], SystemMessage):
            self.messages[0] = SystemMessage(content=prompt)
        else:
            self.messages.insert(0, SystemMessage(content=prompt))

    def add_user(self, content: str) -> UserMessage:
        m = UserMessage(content=content)
        self.messages.append(m)
        return m

    def add_assistant(self, message: AssistantMessage) -> None:
        self.messages.append(message)

    def add_tool_result(self, tool_call_id: str, name: str, content: str) -> None:
        self.messages.append(
            ToolMessage(tool_call_id=tool_call_id, name=name, content=content)
        )

    def fork(self) -> "Thread":
        clone = Thread(metadata=copy.deepcopy(self.metadata))
        clone.messages = copy.deepcopy(self.messages)
        return clone

    def snapshot(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "created_at": self.created_at,
            "metadata": self.metadata,
            "messages": [m.model_dump() for m in self.messages],
        }
