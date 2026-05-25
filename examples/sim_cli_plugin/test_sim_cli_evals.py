"""Run sim_cli YAML eval set in scripted-LLM mode.

Setup state (e.g. `pre_running: [collector]`) is applied by the
framework via setup hooks registered in sim_cli_plugin/eval_setup.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

import pytest

from agentkit import App
from agentkit.eval import EvalRunner, ScriptedLLM, load_cases
from agentkit.eval.scripted_llm import script_from_case_expected
from agentkit.harness.base import Harness
from agentkit.skills.loader import SkillLoader
from agentkit.tools.registry import ToolRegistry

from sim_cli_plugin import (
    SIM_CLI_TOOLS,
    SimCliArtifactFactory,
    SimCliPromptBuilder,
    simgraph_cli_harness_hook,
)
import sim_cli_plugin.eval_setup  # noqa: F401 — side-effect: registers hooks


def make_app(script):
    skills = SkillLoader(HERE / "sim_cli_plugin" / "skills").discover()
    return App(
        tools=ToolRegistry(SIM_CLI_TOOLS),
        llm=ScriptedLLM(script),
        harness=Harness([simgraph_cli_harness_hook]),
        prompt_builder=SimCliPromptBuilder(skills=skills),
        artifact_factory=SimCliArtifactFactory(),
    )


CASES = load_cases(HERE / "evals")


@pytest.mark.parametrize("case", CASES, ids=[c.id for c in CASES])
async def test_case(case):
    script = script_from_case_expected(case)
    res = await EvalRunner(make_app(script)).run(case)
    assert res.passed, "\n".join(res.reasons) + f"\n  observed: {[o.name for o in res.observed_calls]}\n  text: {res.observed_text!r}"
