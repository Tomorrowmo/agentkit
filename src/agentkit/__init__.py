"""agentkit — lightweight, pluggable agent framework.

Re-exports the two surfaces a host application normally needs:
the App entry point and the tool decorator.
"""

from agentkit.plugin.app import App
from agentkit.tools.decorator import tool

__all__ = ["App", "tool"]
__version__ = "0.0.1"
