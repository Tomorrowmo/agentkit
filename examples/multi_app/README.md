# multi_app — chatcfd + simgraph in one host

Two reference plugins, one agentkit App. Demonstrates that the
framework lets unrelated domains share infrastructure without bleeding
into each other.

## What this demo proves

| Concern | Where it lives | How they compose |
|---|---|---|
| **Tools** | each plugin's `tools.py` | merge into one `ToolRegistry` |
| **System prompt** | each plugin's `PromptBuilder` | `UnionPromptBuilder` concatenates |
| **Artifacts** | each plugin's `ArtifactFactory` | `UnionArtifactFactory` first-non-None wins |
| **Harness rules** | each plugin's hooks | `Harness([h1, h2])` — built-in |
| **Skills** | each plugin's `skills/*.md` | merged at `SkillLoader` time |
| **Thread / LLM / IPC** | agentkit | unchanged — one shared instance |

**Zero changes to agentkit, zero changes to either plugin.** The
composition lives in `main.py` of this folder.

## A realistic cross-app conversation

```
USER: 找张伟做的 Ma6 已收敛算例，然后加载第一个分析气动力
                 ↓ (simgraph.query_graph)
ASSISTANT: 找到 f001: /shared/aero/2024_03/case_run023/, Ma=6.0...
                 ↓ (chatcfd.loadFile, path from f001.path)
ASSISTANT: 已加载 wing/fuselage/wake 三个 zone...
                 ↓ (chatcfd.calculate, method="force")
ASSISTANT: Fx=-2.3, Fy=0.1, Fz=8.7 (N)
```

The agent orchestrates tools from both plugins in one turn. The two
plugins know **nothing** about each other.

## Tool relationship matrix

| | chatcfd tools | simgraph tools |
|---|---|---|
| **shape** | stateful (`session_id` chain) | mostly stateless |
| **state location** | in-process VTK session | external Neo4j |
| **return data size** | binary mesh blobs | small JSON cards |
| **typical caller** | "analyze X" | "find / compare / trace X" |
| **artifact kind** | mesh / table / file | result_list / data_card / subgraph |
| **harness rule** | path whitelist (case root) | path whitelist (index root) |

**They never call each other.** Cross-domain workflows are orchestrated
by the LLM — it sees both tool lists, picks the right one per step.
This is the cleanest possible coupling: zero.

## Run

```bash
export ANTHROPIC_API_KEY=...
python examples/multi_app/main.py
```

`ws://127.0.0.1:8767/agent`
