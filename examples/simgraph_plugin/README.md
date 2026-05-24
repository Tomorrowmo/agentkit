# simgraph_plugin — reference host for a graph-based simulation index

A second reference host built on agentkit. Demonstrates that the
framework abstraction holds when the host is **structurally different
from chatcfd**:

| | chatcfd | simgraph |
|---|---|---|
| domain | single CFD case analysis | repository-wide simulation index |
| storage | in-process VTK session | Neo4j graph + LLM-extracted metadata |
| tool shape | session_id stateful loop | mostly stateless NL→Cypher queries |
| artifact | mesh / table / file | data card / graph subgraph |
| user verb | "analyze", "calculate" | "find", "compare", "trace" |

Tools (mocked, but match the real simgraph wire shape):

- `ingest_file(path)` — scan a sim file, kick off metadata extraction
- `extract_metadata(file_id)` — LLM-extracts case params with confidence
- `query_graph(natural_language)` — NL → Cypher → Neo4j (here: fake)
- `get_card(file_id)` — full data card for one file
- `find_similar(file_id, k=5)` — graph similarity
- `trace_provenance(file_id)` — upstream mesh/setup files

## Run

```bash
export ANTHROPIC_API_KEY=...
python examples/simgraph_plugin/main.py
```

`ws://127.0.0.1:8766/agent` — note: different port from chatcfd so
they can run side by side on one machine.

## Why this exists

M4 of the agentkit roadmap is "validate the abstraction with a second
project." Building this plugin **without touching agentkit** is the
proof: every line of CFD-shaped or graph-shaped logic lives in its
own plugin package; the framework holds both up unchanged.

See [doc/m4-analysis.md](../../doc/m4-analysis.md) for the cross-app
comparison and what the abstraction proved (or failed to prove).
