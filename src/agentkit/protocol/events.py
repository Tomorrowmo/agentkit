"""StreamEvent — what the IPC layer emits to clients.

Discriminated union on `type`. Add new events by adding a new model and
extending the union — clients ignore unknown types.
"""

from __future__ import annotations

from typing import Any, Literal, Union

from pydantic import BaseModel, Field


class ThreadStartedEvent(BaseModel):
    type: Literal["thread_started"] = "thread_started"
    thread_id: str


class AssistantTextEvent(BaseModel):
    type: Literal["assistant_text"] = "assistant_text"
    delta: str


class ToolCallEvent(BaseModel):
    type: Literal["tool_call"] = "tool_call"
    call_id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolResultEvent(BaseModel):
    type: Literal["tool_result"] = "tool_result"
    call_id: str
    name: str
    result: Any = None
    error: str | None = None


class ArtifactEvent(BaseModel):
    """Emitted by host plugins (ArtifactFactory). Framework just carries it."""

    type: Literal["artifact"] = "artifact"
    kind: str
    payload: dict[str, Any] = Field(default_factory=dict)


class TurnFinishedEvent(BaseModel):
    type: Literal["turn_finished"] = "turn_finished"
    thread_id: str


class ErrorEvent(BaseModel):
    type: Literal["error"] = "error"
    message: str
    detail: dict[str, Any] | None = None


StreamEvent = Union[
    ThreadStartedEvent,
    AssistantTextEvent,
    ToolCallEvent,
    ToolResultEvent,
    ArtifactEvent,
    TurnFinishedEvent,
    ErrorEvent,
]
