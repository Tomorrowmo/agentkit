# agentkit

Lightweight, pluggable agent framework. **Skeleton only — business logic lives in host applications.**

> Status: M1 (core scaffold). Design: [doc/design.md](doc/design.md).

## Three non-negotiable principles

1. **No business code in the framework.** chatcfd / simgraph / future projects plug in from the outside.
2. **The framework is not better when bigger.** Modules earn their place by being independently useful.
3. **Tools, skills, prompts, and plugins evolve independently** — none of them should depend on framework internals.

## Layers

```
ipc/        ── WebSocket / stdio / HTTP transports
plugin/     ── host-app entry point (App, PromptBuilder, ArtifactFactory, ContextHook)
session/    ── Thread / Turn / ThreadPool / Compact
tools/      ── ToolExecutor ABC, Registry, Router, Exposure (Direct/Deferred/Hidden)
mcp/        ── MCP client pool + adapter + proxy executor
llm/        ── LiteLLM wrapper (retry/timeout/stream)
harness/    ── before_call / after_call safety hooks
skills/     ── markdown+frontmatter loader
observability/ insight_log + trace
protocol/   ── pure Pydantic contracts (the constitution)
```

## Quick start

```bash
pip install -e .
python examples/hello_agent/main.py
```

Then open `ws://localhost:8765/agent` and send `{"type": "user_message", "content": "say hello"}`.

## Writing a tool (host app)

```python
from agentkit.tools import tool

@tool(name="echo", description="Echo the input back.")
async def echo(text: str) -> dict:
    return {"text": text}
```

## Embedding agentkit (host app)

```python
from agentkit import App
from agentkit.tools import ToolRegistry

registry = ToolRegistry()
registry.register(echo)

App(tools=registry).run(host="0.0.0.0", port=8765)
```

See [examples/hello_agent](examples/hello_agent) for the full reference.
