---
name: sim-cli-ops
description: Operating discipline for the simgraph CLI
trigger: always
---

When the user asks to start/stop/check services:

1. `cli_status` first — never trust your memory.
2. If a service is already running and they ask to start it: report that, do NOT restart.
3. Order for "start everything":
   `init_config` → `start_post_service` → `start_collector` → `start_mcp`
4. Never invent PIDs. If `pid` is missing from the result (dry_run), say so.
5. If `cli_version` returns an error mentioning PATH, stop and ask the user to install or set `SIMGRAPH_BIN`.
