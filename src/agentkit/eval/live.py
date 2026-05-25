"""Live-LLM eval mode helpers.

Difference from scripted mode:
  - scripted: framework wiring test. LLM is replaced with ScriptedLLM
              driven by case.expected_calls. Asserts that GIVEN the LLM
              picks these tools with these args, the framework dispatches,
              harness verdicts, artifact factory, and text round-trips
              are correct.
  - live: real LLM behavior test. Uses the host's actual LLMClient. The
          Runner observes what the LLM actually did and compares against
          expected_calls. A divergence is signal — either the prompt
          drifted, the model regressed, or the expectation is wrong.

Both modes use the same EvalRunner; only the App's LLM differs. This
module provides convenience builders + a switch.
"""

from __future__ import annotations

import os
from enum import Enum
from typing import Callable

from agentkit.eval.case import EvalCase
from agentkit.eval.runner import CaseResult, EvalRunner
from agentkit.eval.scripted_llm import ScriptedLLM, script_from_case_expected
from agentkit.llm.client import LLMClient
from agentkit.plugin.app import App


class EvalMode(str, Enum):
    SCRIPTED = "scripted"
    LIVE = "live"


def resolve_mode(explicit: str | None = None) -> EvalMode:
    if explicit:
        return EvalMode(explicit.lower())
    raw = os.environ.get("AGENTKIT_EVAL_MODE", "scripted").lower()
    return EvalMode(raw)


# Builder type: takes an LLMClient, returns a configured App.
AppBuilder = Callable[[LLMClient], App]


async def run_cases(
    cases: list[EvalCase],
    builder: AppBuilder,
    mode: EvalMode = EvalMode.SCRIPTED,
    live_model: str | None = None,
) -> list[CaseResult]:
    """Run cases under the requested mode. Returns CaseResults in order."""
    results: list[CaseResult] = []

    if mode == EvalMode.LIVE:
        live = LLMClient(model=live_model or os.environ.get("AGENTKIT_MODEL", "gpt-4o-mini"))
        app = builder(live)
        runner = EvalRunner(app)
        for case in cases:
            results.append(await runner.run(case))
        return results

    # SCRIPTED: fresh ScriptedLLM per case (script is consumed).
    for case in cases:
        scripted = ScriptedLLM(script_from_case_expected(case))
        app = builder(scripted)
        runner = EvalRunner(app)
        results.append(await runner.run(case))
    return results
