"""Typed errors. Framework raises these; host code can catch by type."""


class AgentError(Exception):
    """Base class — all framework errors derive from this."""


class ToolNotFound(AgentError):
    pass


class ToolError(AgentError):
    """Wraps an exception raised inside a tool handler."""

    def __init__(self, tool_name: str, original: BaseException):
        super().__init__(f"{tool_name}: {original}")
        self.tool_name = tool_name
        self.original = original


class HarnessRejected(AgentError):
    """Harness refused a tool call. `reason` is shown to the LLM."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason
