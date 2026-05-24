"""Reference CFD plugin for agentkit.

What you'd see in a real chatcfd host:
  - CFD_TOOLS: 6 tools (mocked here; real impl forwards to MCP server)
  - CFDPromptBuilder: weaves loaded skills + active case into system prompt
  - CFDArtifactFactory: turns load/calculate results into UI artifacts
  - CFDMemoryHook: example ContextHook (recall before turn, extract after)
  - cfd_harness_hook: path whitelist (rejects reads outside the case root)
"""

from chatcfd_plugin.artifact_factory import CFDArtifactFactory
from chatcfd_plugin.hooks import CFDMemoryHook, cfd_harness_hook
from chatcfd_plugin.prompt_builder import CFDPromptBuilder, CFDState
from chatcfd_plugin.tools import CFD_TOOLS

__all__ = [
    "CFD_TOOLS",
    "CFDArtifactFactory",
    "CFDMemoryHook",
    "CFDPromptBuilder",
    "CFDState",
    "cfd_harness_hook",
]
