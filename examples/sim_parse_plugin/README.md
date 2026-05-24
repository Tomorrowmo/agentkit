# sim_parse_plugin — wrap simgraph's solver parsers as agent tools

The real `simgraph.modules.ingest.parsers` has CGNS / OpenFOAM /
Fluent parsers. They share a common shape:

```python
class XParser(BaseParser):
    extensions = [".x"]
    solver_name = "X"
    def detect(self, file_path) -> bool: ...
    def parse(self, case_dir) -> ParseResult: ...
```

This plugin lifts that contract straight into agent tools without
modifying simgraph:

| simgraph parser | tools exposed |
|---|---|
| `CGNSParser` | `detect_format(path)`, `parse_cgns(path)` |
| `OpenFOAMParser` | `detect_format(path)`, `parse_openfoam(path)` |
| `FluentParser` | `detect_format(path)`, `parse_fluent(path)` |
| `ParserRegistry` | `list_parsers()`, `auto_parse(path)` |

**Tool relationships**:
- `detect_format` is the dispatch layer — the LLM calls it first
- `auto_parse` is the "do the right thing" composite — for users who don't care
- The three `parse_<solver>` are escape hatches when the user wants
  to force a specific parser

## Design — do simgraph's parsers need refactoring?

**Short answer: no.** `BaseParser`'s contract is already
`detect / parse` — exactly what an agent tool wants. The plugin
adapts it without changing simgraph code:

```python
@tool(description="...")
async def parse_openfoam(path: str) -> dict:
    from simgraph.modules.ingest.parsers import OpenFOAMParser  # real import
    p = OpenFOAMParser()
    if not p.detect(path):
        return {"error": "not an OpenFOAM case"}
    result = p.parse(path)
    return {"summary": ..., "solver": result.solver, "metadata": result.metadata, ...}
```

The reference impl below uses **mocked parsers** so it runs without
simgraph installed. The wrapping pattern is the same either way.

## Run

```bash
python examples/sim_parse_plugin/main.py
```

`ws://127.0.0.1:8769/agent` and `http://127.0.0.1:8769/` for the UI.
