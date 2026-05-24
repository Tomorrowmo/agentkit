"""Reference simgraph plugin for agentkit.

Exports:
  - SIMGRAPH_TOOLS: 6 tools (mocked Neo4j + LLM-extracted metadata)
  - SimGraphPromptBuilder: graph-search-oriented system prompt
  - SimGraphArtifactFactory: data cards, subgraphs, file links
  - simgraph_harness_hook: rejects writes outside the index
"""

from simgraph_plugin.artifact_factory import SimGraphArtifactFactory
from simgraph_plugin.hooks import simgraph_harness_hook
from simgraph_plugin.prompt_builder import SimGraphPromptBuilder, SimGraphState
from simgraph_plugin.tools import SIMGRAPH_TOOLS

__all__ = [
    "SIMGRAPH_TOOLS",
    "SimGraphArtifactFactory",
    "SimGraphPromptBuilder",
    "SimGraphState",
    "simgraph_harness_hook",
]
