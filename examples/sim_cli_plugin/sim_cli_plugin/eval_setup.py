"""Eval setup hooks + App builder for sim_cli.

Importing this module is enough to register the hooks with agentkit's
DEFAULT_REGISTRY. The plugin's test_evals.py imports it; the production
main.py does not (the prod path doesn't run evals).
"""

from __future__ import annotations

from pathlib import Path

from agentkit import App
from agentkit.eval import setup_hook
from agentkit.harness.base import Harness
from agentkit.llm.client import LLMClient
from agentkit.plugin.app import AppContext
from agentkit.skills.loader import SkillLoader
from agentkit.tools.registry import ToolRegistry

from sim_cli_plugin import (
    SIM_CLI_TOOLS,
    SimCliArtifactFactory,
    SimCliPromptBuilder,
    simgraph_cli_harness_hook,
)
from sim_cli_plugin.tools import process_registry


HERE = Path(__file__).parent.parent  # examples/sim_cli_plugin/


@setup_hook("pre_running", teardown=lambda v, c: process_registry.procs.clear())
def _pre_running(value: list[str], ctx: AppContext) -> None:
    """`pre_running: [collector, mcp]` — seed registry as if those services already up."""
    process_registry.procs.clear()
    for name in value:
        process_registry.add(name, ["simgraph", "c"], pid=12345)


def build_eval_app(llm: LLMClient) -> App:
    """Used by `python -m agentkit.eval run ... --app sim_cli_plugin.eval_setup:build_eval_app`."""
    skills = SkillLoader(HERE / "sim_cli_plugin" / "skills").discover()
    return App(
        tools=ToolRegistry(SIM_CLI_TOOLS),
        llm=llm,
        harness=Harness([simgraph_cli_harness_hook]),
        prompt_builder=SimCliPromptBuilder(skills=skills),
        artifact_factory=SimCliArtifactFactory(),
    )
