"""Run sim_parse YAML eval set in scripted-LLM mode.

Path materialization is handled by the framework via @setup_hook("path")
in sim_parse_plugin/eval_setup.py. /tmp/... → OS tempdir remap is also
applied to the case's expected_calls so they reference the same path.
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

from sim_parse_plugin import (
    SIM_PARSE_TOOLS,
    SimParseArtifactFactory,
    SimParsePromptBuilder,
    sim_parse_harness_hook,
)
from sim_parse_plugin.eval_setup import remap_paths_in_case  # also registers @setup_hook


def make_app(script):
    skills = SkillLoader(HERE / "sim_parse_plugin" / "skills").discover()
    return App(
        tools=ToolRegistry(SIM_PARSE_TOOLS),
        llm=ScriptedLLM(script),
        harness=Harness([sim_parse_harness_hook]),
        prompt_builder=SimParsePromptBuilder(skills=skills),
        artifact_factory=SimParseArtifactFactory(),
    )


CASES = load_cases(HERE / "evals")
for c in CASES:
    remap_paths_in_case(c)


@pytest.mark.parametrize("case", CASES, ids=[c.id for c in CASES])
async def test_case(case):
    script = script_from_case_expected(case)
    res = await EvalRunner(make_app(script)).run(case)
    assert res.passed, "\n".join(res.reasons) + f"\n  observed: {[o.name for o in res.observed_calls]}\n  text: {res.observed_text!r}"
