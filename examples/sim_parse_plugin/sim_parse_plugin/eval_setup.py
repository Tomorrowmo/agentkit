"""Eval setup hooks for sim_parse — auto-create paths referenced by cases.

Cross-platform: case YAMLs may reference /tmp/... (POSIX); on Windows
we remap to the OS tempdir. The remap is also exposed so the case's
expected_calls can be patched (since they reference the same path).
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from agentkit import App
from agentkit.eval import setup_hook
from agentkit.harness.base import Harness
from agentkit.llm.client import LLMClient
from agentkit.plugin.app import AppContext
from agentkit.skills.loader import SkillLoader
from agentkit.tools.registry import ToolRegistry

from sim_parse_plugin import (
    SIM_PARSE_TOOLS,
    SimParseArtifactFactory,
    SimParsePromptBuilder,
    sim_parse_harness_hook,
)


HERE = Path(__file__).parent.parent  # examples/sim_parse_plugin/


_TMP = Path(tempfile.gettempdir())
os.environ.setdefault("SIM_PARSE_ROOT", str(_TMP))


def remap(path: str) -> str:
    """POSIX /tmp/... -> platform tempdir."""
    if path.startswith("/tmp/"):
        return str(_TMP / Path(path[len("/tmp/"):]))
    return path


@setup_hook("path")
def _ensure_path(value: str, ctx: AppContext) -> None:
    target = Path(remap(value))
    if target.suffix:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.touch(exist_ok=True)
    else:
        target.mkdir(parents=True, exist_ok=True)
        if "openfoam_case" in str(target):
            (target / "system").mkdir(exist_ok=True)
            (target / "system" / "controlDict").touch(exist_ok=True)


def remap_paths_in_case(case) -> None:
    """Mutate a case so any /tmp/... refs become the OS-correct path."""
    if case.setup and (p := case.setup.get("path")):
        case.setup["path"] = remap(p)
    for ec in case.expected_calls:
        for k, v in list(ec.args.items()):
            if isinstance(v, str) and v.startswith("/tmp/"):
                ec.args[k] = remap(v)


def build_eval_app(llm: LLMClient) -> App:
    """Used by `python -m agentkit.eval run ... --app sim_parse_plugin.eval_setup:build_eval_app`."""
    skills = SkillLoader(HERE / "sim_parse_plugin" / "skills").discover()
    return App(
        tools=ToolRegistry(SIM_PARSE_TOOLS),
        llm=llm,
        harness=Harness([sim_parse_harness_hook]),
        prompt_builder=SimParsePromptBuilder(skills=skills),
        artifact_factory=SimParseArtifactFactory(),
    )
