"""LLMClient — thin wrapper over LiteLLM.

Why LiteLLM: it normalizes provider differences (OpenAI, Anthropic,
Bedrock, local OpenAI-compatible servers, etc.) into one
`acompletion(...)` API. We add retries, timeouts, and translation
between our protocol Messages and LiteLLM's dict shape.

Streaming: returns an async iterator of delta dicts. Callers reassemble
into AssistantMessage and emit AssistantTextEvent / ToolCallEvent as
they go.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Sequence

from agentkit.protocol.messages import (
    AssistantMessage,
    Message,
    ToolCall,
)
from agentkit.protocol.tool_spec import ToolSpec


def _msg_to_dict(m: Message) -> dict[str, Any]:
    if m.role == "assistant":
        out: dict[str, Any] = {"role": "assistant", "content": m.content or ""}
        if m.tool_calls:
            out["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                    },
                }
                for tc in m.tool_calls
            ]
        return out
    if m.role == "tool":
        return {
            "role": "tool",
            "tool_call_id": m.tool_call_id,
            "name": m.name,
            "content": m.content,
        }
    return {"role": m.role, "content": m.content}


def _spec_to_dict(s: ToolSpec) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": s.name,
            "description": s.description,
            "parameters": s.parameters,
        },
    }


@dataclass
class LLMResponse:
    message: AssistantMessage
    finish_reason: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class LLMClient:
    def __init__(
        self,
        model: str = "gpt-4o-mini",
        timeout: float = 60.0,
        max_retries: int = 2,
        extra_params: dict[str, Any] | None = None,
    ):
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        self.extra_params = extra_params or {}

    async def complete(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec] | None = None,
    ) -> LLMResponse:
        import litellm  # local import — keep cold-start cheap

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": [_msg_to_dict(m) for m in messages],
            "timeout": self.timeout,
            **self.extra_params,
        }
        if tools:
            kwargs["tools"] = [_spec_to_dict(t) for t in tools]

        last_exc: BaseException | None = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = await litellm.acompletion(**kwargs)
                return self._parse(resp)
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if attempt < self.max_retries:
                    await asyncio.sleep(0.5 * (2 ** attempt))
        raise RuntimeError(f"LLM call failed after retries: {last_exc}") from last_exc

    async def stream(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        import litellm

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": [_msg_to_dict(m) for m in messages],
            "timeout": self.timeout,
            "stream": True,
            **self.extra_params,
        }
        if tools:
            kwargs["tools"] = [_spec_to_dict(t) for t in tools]

        async for chunk in await litellm.acompletion(**kwargs):
            yield chunk if isinstance(chunk, dict) else chunk.model_dump()

    @staticmethod
    def _parse(resp: Any) -> LLMResponse:
        data = resp if isinstance(resp, dict) else resp.model_dump()
        choice = data["choices"][0]
        msg = choice["message"]
        tool_calls: list[ToolCall] = []
        for tc in msg.get("tool_calls") or []:
            fn = tc.get("function", {})
            args_raw = fn.get("arguments") or "{}"
            try:
                args = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
            except json.JSONDecodeError:
                args = {"_raw": args_raw}
            tool_calls.append(ToolCall(id=tc.get("id") or "", name=fn.get("name", ""), arguments=args))
        return LLMResponse(
            message=AssistantMessage(
                content=msg.get("content"),
                tool_calls=tool_calls,
            ),
            finish_reason=choice.get("finish_reason"),
            raw=data,
        )
