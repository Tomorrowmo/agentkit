"""hello_agent — minimal agentkit demo.

What it shows:
  - Authoring a tool with the @tool decorator
  - Constructing an App
  - Running the WebSocket server

Set an LLM key in env (e.g. ANTHROPIC_API_KEY / OPENAI_API_KEY) before
running. Pick a model your key works with via the AGENTKIT_MODEL env
var; default below is gpt-4o-mini.
"""

from __future__ import annotations

import os

from agentkit import App, tool
from agentkit.llm.client import LLMClient
from agentkit.tools.registry import ToolRegistry


@tool(description="Echo whatever the caller passes in.")
async def echo(text: str) -> dict:
    return {"text": text}


@tool(description="Add two integers and return the sum.")
async def add(a: int, b: int) -> dict:
    return {"sum": a + b}


def main() -> None:
    registry = ToolRegistry([echo, add])
    llm = LLMClient(model=os.environ.get("AGENTKIT_MODEL", "gpt-4o-mini"))
    App(tools=registry, llm=llm).run(host="127.0.0.1", port=8765)


if __name__ == "__main__":
    main()
