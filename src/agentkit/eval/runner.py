"""EvalRunner — execute a Case against an App, return a CaseResult.

Captures observed tool_calls + assistant text by sniffing the
StreamEvents the App produces. Compares against the case expectations
and produces a structured pass/fail with reasons.

The Runner is LLM-agnostic: pass either a ScriptedLLM (deterministic)
or a real LLMClient (real model behavior).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agentkit.eval.case import EvalCase, ExpectedCall, match_args
from agentkit.eval.setup import DEFAULT_REGISTRY, SetupRegistry
from agentkit.plugin.app import App
from agentkit.protocol.events import (
    AssistantTextEvent,
    ToolCallEvent,
    ToolResultEvent,
)


@dataclass
class ObservedCall:
    name: str
    arguments: dict[str, Any]
    result: Any = None
    error: str | None = None


@dataclass
class CaseResult:
    case_id: str
    passed: bool
    reasons: list[str] = field(default_factory=list)
    observed_calls: list[ObservedCall] = field(default_factory=list)
    observed_text: str = ""

    def summary(self) -> str:
        verdict = "PASS" if self.passed else "FAIL"
        body = "; ".join(self.reasons) if self.reasons else "ok"
        return f"[{verdict}] {self.case_id}: {body}"


class EvalRunner:
    def __init__(self, app: App, setup_registry: SetupRegistry | None = None):
        self.app = app
        self.setup_registry = setup_registry or DEFAULT_REGISTRY

    async def run(self, case: EvalCase) -> CaseResult:
        # Apply registered setup hooks for keys present in case.setup.
        # Plugins register these once at import time via @setup_hook("key").
        applied = await self.setup_registry.apply(case.setup or {}, self.app.context)

        thread = self.app.open_thread()
        thread.metadata["eval_setup"] = case.setup

        observed: list[ObservedCall] = []
        text_parts: list[str] = []
        call_id_to_obs: dict[str, ObservedCall] = {}

        try:
            async for event in self.app.turn(thread, case.user_input):
                if isinstance(event, AssistantTextEvent):
                    text_parts.append(event.delta)
                elif isinstance(event, ToolCallEvent):
                    obs = ObservedCall(name=event.name, arguments=event.arguments)
                    observed.append(obs)
                    call_id_to_obs[event.call_id] = obs
                elif isinstance(event, ToolResultEvent):
                    obs = call_id_to_obs.get(event.call_id)
                    if obs is not None:
                        obs.result = event.result
                        obs.error = event.error
        finally:
            await self.setup_registry.teardown(applied, self.app.context)

        observed_text = "".join(text_parts)
        passed, reasons = self._evaluate(case, observed, observed_text)
        return CaseResult(
            case_id=case.id,
            passed=passed,
            reasons=reasons,
            observed_calls=observed,
            observed_text=observed_text,
        )

    @staticmethod
    def _evaluate(
        case: EvalCase,
        observed: list[ObservedCall],
        observed_text: str,
    ) -> tuple[bool, list[str]]:
        reasons: list[str] = []

        # Forbidden calls / text first — clearest signals.
        observed_names = [o.name for o in observed]
        for fb in case.forbidden_calls:
            if fb in observed_names:
                reasons.append(f"forbidden_call appeared: {fb}")
        for ft in case.forbidden_text_includes:
            if ft and ft in observed_text:
                reasons.append(f"forbidden_text appeared: {ft!r}")
        for inc in case.expected_text_includes:
            if inc and inc not in observed_text:
                reasons.append(f"missing expected_text: {inc!r}")

        # Expected calls — order-sensitive unless loose_order.
        if case.loose_order:
            reasons.extend(_match_loose(case.expected_calls, observed))
        else:
            reasons.extend(_match_strict(case.expected_calls, observed))

        return (len(reasons) == 0), reasons


def _match_strict(expected: list[ExpectedCall], observed: list[ObservedCall]) -> list[str]:
    reasons: list[str] = []
    j = 0
    for ec in expected:
        # Skip ahead in observed until we either match or run out.
        matched = False
        while j < len(observed):
            o = observed[j]
            if o.name == ec.name:
                ok, why = match_args(ec.args, o.arguments)
                if ok:
                    matched = True
                    j += 1
                    break
                if not ec.optional:
                    reasons.append(f"call[{ec.name}] arg mismatch: {why}")
                    j += 1
                    break
            j += 1
        if not matched and not ec.optional:
            reasons.append(f"missing expected call: {ec.name}({ec.args})")
    return reasons


def _match_loose(expected: list[ExpectedCall], observed: list[ObservedCall]) -> list[str]:
    reasons: list[str] = []
    pool = list(observed)
    for ec in expected:
        for i, o in enumerate(pool):
            if o.name == ec.name:
                ok, _ = match_args(ec.args, o.arguments)
                if ok:
                    pool.pop(i)
                    break
        else:
            if not ec.optional:
                reasons.append(f"missing expected call (loose): {ec.name}")
    return reasons
