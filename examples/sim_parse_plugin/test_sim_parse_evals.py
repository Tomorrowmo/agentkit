"""Run sim_parse YAML eval set in scripted-LLM mode.

Setup pre-creates the paths the cases reference (so detect_format and
the harness whitelist both succeed) inside a tmp scratch directory.
"""

from __future__ import annotations

import os
import sys
import tempfile
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


_TMP = Path(tempfile.gettempdir())
os.environ.setdefault("SIM_PARSE_ROOT", str(_TMP))


def _ensure_path(p: str) -> None:
    """Create the path used by the eval case so detect_format finds something."""
    target = Path(p)
    if str(target).startswith("/tmp/"):
        target = _TMP / target.relative_to("/tmp/")
    if target.suffix:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.touch(exist_ok=True)
    else:
        target.mkdir(parents=True, exist_ok=True)
        if "openfoam_case" in str(target):
            (target / "system").mkdir(exist_ok=True)
            (target / "system" / "controlDict").touch(exist_ok=True)


def make_app(script):
    skills = SkillLoader(HERE / "sim_parse_plugin" / "skills").discover()
    return App(
        tools=ToolRegistry(SIM_PARSE_TOOLS),
        llm=ScriptedLLM(script),
        harness=Harness([sim_parse_harness_hook]),
        prompt_builder=SimParsePromptBuilder(skills=skills),
        artifact_factory=SimParseArtifactFactory(),
    )


def remap_paths_in_case(case):
    """Rewrite /tmp/... refs to OS tmpdir so cases run on Windows."""
    if (sp := case.setup.get("path")):
        case.setup["path"] = str(_TMP / Path(sp).relative_to("/tmp/")) if sp.startswith("/tmp/") else sp
    for ec in case.expected_calls:
        for k, v in list(ec.args.items()):
            if isinstance(v, str) and v.startswith("/tmp/"):
                ec.args[k] = str(_TMP / Path(v).relative_to("/tmp/"))


CASES = load_cases(HERE / "evals")
for c in CASES:
    remap_paths_in_case(c)
    if (p := c.setup.get("path")):
        _ensure_path(p)


@pytest.mark.parametrize("case", CASES, ids=[c.id for c in CASES])
async def test_case(case):
    script = script_from_case_expected(case)
    res = await EvalRunner(make_app(script)).run(case)
    assert res.passed, "\n".join(res.reasons) + f"\n  observed: {[o.name for o in res.observed_calls]}\n  text: {res.observed_text!r}"
