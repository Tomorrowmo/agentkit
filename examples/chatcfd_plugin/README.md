# chatcfd_plugin — reference host on agentkit

This is **not the chatcfd production code**. It's a self-contained, runnable
plugin that demonstrates how a CFD analysis app builds on agentkit using:

- **Local tools** (`@tool`-decorated functions) — `loadFile`, `calculate`,
  `listFiles`, `getMethodTemplate`, `compare`, `exportData`
- **CFDPromptBuilder** — composes system prompt from skills + active-case state
- **CFDArtifactFactory** — turns `loadFile` / `calculate` results into UI artifacts
- **CFDMemoryHook** — illustrative `ContextHook` that injects recall before each turn
- **CFDHarnessHook** — path whitelist policy (no reads outside the case dir)
- **Skills as markdown** — `chatcfd_plugin/skills/*.md`

It uses **fake compute** (random data, predefined responses) so it runs without VTK
or a real solver. Real chatcfd swaps these for MCP proxy executors that round-trip
to the `post_service` MCP server — the rest of the plugin doesn't change.

## Run

```bash
export ANTHROPIC_API_KEY=...
export AGENTKIT_MODEL=claude-sonnet-4-6
python examples/chatcfd_plugin/main.py
```

Then connect a WebSocket client to `ws://127.0.0.1:8765/agent` and ask:

> List the cases. Then load the first one and tell me about it.

You should see a `thread_started`, a stream of `assistant_text`, two `tool_call` /
`tool_result` pairs, an `artifact` event for the loaded mesh, and `turn_finished`.

## What this proves about the framework

1. **Zero edits to agentkit** were needed to build it.
2. **Six CFD tools** went from zero to runnable by writing one Python module.
3. **The CFD-specific system prompt** lives entirely in `prompt_builder.py` — no
   string concatenation hidden in the framework.
4. **Mesh blobs** would be too big to round-trip through the LLM, but the
   framework's `_strip_binary` convention keeps the LLM's view clean while the
   `ArtifactFactory` still sees the full payload.

## Migration path for real chatcfd

| Reference (this folder) | Production chatcfd |
|---|---|
| local `@tool` mocks | `App(mcp_servers=["http://localhost:8000/sse"])` |
| `chatcfd_plugin/skills/*.md` | `chatcfd/agent/skills/*.md` (same loader) |
| `CFDArtifactFactory` (hash mesh) | `CFDArtifactFactory` (real VTK.js descriptor) |
| `CFDMemoryHook` (no-op) | `CFDMemoryHook` (mempalace recall) |
| `CFDHarnessHook` (whitelist `/cases`) | same hook, real path whitelist |
