"""ScriptedLLM — deterministic LLM replacement for eval runs.

Lets you replay an EvalCase without a real API key. The script is a
list of ScriptedTurns: each turn either emits tool_calls (and waits
for the framework to dispatch them, returning a tool_result) or emits
final assistant text.

This is the same trick simgraph's eval doc says to use:
   "意图层用 mock LLM 固定 tool_calls 序列断言"

What ScriptedLLM does NOT do: validate that a real LLM would have
made the same choices. For that, use the real LLMClient. ScriptedLLM
validates that GIVEN the LLM picks these tools, the framework wires
them through correctly (dispatch / harness / artifacts / state).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

from agentkit.llm.client import LLMClient, LLMResponse
from agentkit.protocol.messages import AssistantMessage, Message, ToolCall


@dataclass
class ScriptedTurn:
    """Either tool_calls (will be dispatched, then ScriptedLLM is called again)
    OR text (final assistant reply for this turn). Set one or both."""

    tool_calls: list[ToolCall] = field(default_factory=list)
    text: str | None = None


class ScriptedLLM(LLMClient):
    def __init__(self, script: Sequence[ScriptedTurn]):
        super().__init__(model="scripted")
        self._script = list(script)
        self.invocations = 0

    async def complete(  # type: ignore[override]
        self,
        messages: Sequence[Message],
        tools: Sequence[Any] | None = None,
    ) -> LLMResponse:
        self.invocations += 1
        if not self._script:
            # Out of script — return a benign stop so the loop terminates.
            return LLMResponse(
                message=AssistantMessage(content="[scripted: end]"),
                finish_reason="stop",
            )
        turn = self._script.pop(0)
        return LLMResponse(
            message=AssistantMessage(content=turn.text, tool_calls=list(turn.tool_calls)),
            finish_reason="tool_calls" if turn.tool_calls else "stop",
        )

    async def complete_streaming(  # type: ignore[override]
        self,
        messages,
        on_text_delta,
        tools=None,
    ) -> LLMResponse:
        resp = await self.complete(messages, tools=tools)
        if resp.message.content:
            ret = on_text_delta(resp.message.content)
            if hasattr(ret, "__await__"):
                await ret
        return resp


def _matcher_to_value(want: Any) -> Any:
    """Turn a matcher dict into a concrete value that satisfies its constraint.

    For literal values, return as-is. For matcher dicts:
      __any__       → "x"
      __regex__     → a hex-ish placeholder; if regex looks like ^[a-f0-9]{N}$,
                      produce N zeros, which both passes match_args (regex) and
                      gives the underlying tool a syntactically valid string.
      __contains__  → the needle itself (it trivially contains itself)
    """
    if not isinstance(want, dict):
        return want
    if "__any__" in want:
        return "x"
    if "__contains__" in want:
        return want["__contains__"]
    if "__regex__" in want:
        import re as _re
        pat = want["__regex__"]
        m = _re.fullmatch(r"\^\[a-f0-9\]\{(\d+)\}\$", pat)
        if m:
            return "0" * int(m.group(1))
        # Generic fallback: try the pattern literally minus regex anchors
        return _re.sub(r"[\^$\\.\[\]\(\)\{\}+*?|]", "", pat) or "placeholder"
    return want  # opaque dict, pass through


def script_from_case_expected(case) -> list[ScriptedTurn]:  # noqa: ANN001
    """Build a default script that emits the case's expected_calls in order,
    then a final text combining expected_text_includes.

    Matcher meta-dicts in expected args are replaced by a concrete placeholder
    that satisfies the matcher (e.g. __regex__ → a string that matches).
    """
    from agentkit.eval.case import EvalCase

    assert isinstance(case, EvalCase)
    turns: list[ScriptedTurn] = []
    for i, ec in enumerate(case.expected_calls):
        if ec.optional:
            continue
        args = {k: _matcher_to_value(v) for k, v in ec.args.items()}
        turns.append(
            ScriptedTurn(
                tool_calls=[ToolCall(id=f"call_{i}", name=ec.name, arguments=args)]
            )
        )
    final = " ".join(case.expected_text_includes) or "done."
    turns.append(ScriptedTurn(text=final))
    return turns
