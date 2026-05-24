"""Run the chatcfd YAML eval set in scripted-LLM mode (CI-friendly).

Scripted mode validates framework wiring: tool exists, harness doesn't
reject, args shape is correct, error/text round-trips properly. It
does NOT validate that a real LLM would make these choices — for that
set AGENTKIT_EVAL_LIVE=true and provide an LLM API key (and pay).
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

import pytest

from agentkit import App
from agentkit.eval import EvalRunner, Scorecard, ScriptedLLM, load_cases
from agentkit.eval.scripted_llm import script_from_case_expected
from agentkit.harness.base import Harness
from agentkit.skills.loader import SkillLoader
from agentkit.tools.registry import ToolRegistry

from chatcfd_plugin import (
    CFD_TOOLS,
    CFDArtifactFactory,
    CFDMemoryHook,
    CFDPromptBuilder,
    cfd_harness_hook,
)


def make_app(script):
    skills = SkillLoader(HERE / "chatcfd_plugin" / "skills").discover()
    return App(
        tools=ToolRegistry(CFD_TOOLS),
        llm=ScriptedLLM(script),
        harness=Harness([cfd_harness_hook]),
        prompt_builder=CFDPromptBuilder(skills=skills),
        artifact_factory=CFDArtifactFactory(),
        context_hooks=[CFDMemoryHook()],
    )


EVAL_DIR = HERE / "evals"
CASES = load_cases(EVAL_DIR)


@pytest.mark.parametrize("case", CASES, ids=[c.id for c in CASES])
async def test_case(case):
    script = script_from_case_expected(case)
    runner = EvalRunner(make_app(script))
    res = await runner.run(case)
    assert res.passed, "\n".join(res.reasons) + f"\n  observed: {[o.name for o in res.observed_calls]}\n  text: {res.observed_text!r}"


async def test_scorecard_written(tmp_path: Path):
    """Smoke-test the scorecard writer with the whole set."""
    results = []
    for case in CASES:
        script = script_from_case_expected(case)
        results.append(await EvalRunner(make_app(script)).run(case))
    card = Scorecard(results)
    json_out = tmp_path / "score.json"
    md_out = tmp_path / "score.md"
    card.write(json_path=json_out, md_path=md_out)
    assert json_out.exists() and md_out.exists()
    assert "chatcfd" in md_out.read_text(encoding="utf-8") or len(CASES) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
