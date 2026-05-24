# sim_cli_plugin — wrap simgraph's CLI as agent tools

The real `simgraph` CLI exposes commands like `collector`, `mcp`,
`post-service`, `mempalace`, `init` — typically operators run them by
hand at the terminal. This plugin lets the agent drive them:

| simgraph CLI | tool name | what it does |
|---|---|---|
| `simgraph c` | `start_collector` | Start the directory-watcher collector |
| `simgraph mcp` | `start_mcp` | Start the MCP SSE server |
| `simgraph post-service` | `start_post_service` | Start the embedded post_service MCP |
| `simgraph init` | `init_config` | (Re)write `simgraph.toml` from defaults |
| `simgraph --version` | `cli_version` | Return version string |
| (status) | `cli_status` | Report which background processes are alive |

This plugin is **safe-by-default**: every tool that spawns a process
goes through `simgraph_cli_harness_hook`, which can be tightened to a
binary path whitelist in production. The reference impl uses a fake
backend that records spawns without actually executing.

## Design note — tools as the agent's interface to ops

The simgraph CLI is **ops surface**. Wrapping it lets the agent:
- Diagnose: "is the collector running? if not start it"
- Compose: "init config then start collector and mcp together"
- Recover: "post-service crashed, restart it"

The wrapping is mechanical — one `@tool` per subcommand — which is
exactly the point. **No refactoring of simgraph CLI is needed.** The
plugin is a thin adapter: it calls `subprocess.Popen(["simgraph", ...])`
and reports status. simgraph itself doesn't know it's being driven.

## Run

```bash
python examples/sim_cli_plugin/main.py
```

`ws://127.0.0.1:8768/agent` and `http://127.0.0.1:8768/` for the UI.

## Eval

```bash
pytest examples/sim_cli_plugin/test_evals.py -v
```
