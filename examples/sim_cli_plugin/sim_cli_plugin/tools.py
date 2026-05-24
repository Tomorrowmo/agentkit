"""sim_cli tools — wrap each simgraph CLI subcommand as an agent tool.

Each tool:
  1. Builds the argv list (`["simgraph", ...]`)
  2. If `dry_run=True` (default in this reference impl) records the
     spawn in `process_registry` and returns immediately
  3. If `dry_run=False`, calls `subprocess.Popen` and tracks the pid

The dry-run pattern keeps the reference plugin safe to run in CI.
Real deployments flip dry_run False via `SIMCLI_DRY_RUN=false` env.
"""

from __future__ import annotations

import os
import shutil
import time
from dataclasses import dataclass, field

from agentkit.tools import tool


def _real_run() -> bool:
    return os.environ.get("SIMCLI_DRY_RUN", "true").lower() not in ("true", "1", "yes")


@dataclass
class TrackedProcess:
    name: str
    argv: list[str]
    pid: int | None = None
    started_at: float = field(default_factory=time.time)
    status: str = "running"     # running / exited / failed


class ProcessRegistry:
    """In-process record of who we (claim to) have spawned."""

    def __init__(self) -> None:
        self.procs: dict[str, TrackedProcess] = {}

    def add(self, name: str, argv: list[str], pid: int | None) -> TrackedProcess:
        tp = TrackedProcess(name=name, argv=argv, pid=pid)
        self.procs[name] = tp
        return tp

    def alive(self, name: str) -> bool:
        return name in self.procs and self.procs[name].status == "running"

    def remove(self, name: str) -> None:
        self.procs.pop(name, None)


process_registry = ProcessRegistry()


def _spawn(name: str, argv: list[str], wait: bool = False) -> dict:
    pid: int | None = None
    note = "dry_run"
    if _real_run():
        if shutil.which(argv[0]) is None:
            return {"error": f"executable not found on PATH: {argv[0]}"}
        import subprocess
        try:
            if wait:
                cp = subprocess.run(argv, capture_output=True, text=True, timeout=20)
                process_registry.add(name, argv, None)
                return {
                    "summary": f"{name} exited rc={cp.returncode}",
                    "argv": argv,
                    "stdout": cp.stdout[:1000],
                    "stderr": cp.stderr[:1000],
                    "returncode": cp.returncode,
                }
            proc = subprocess.Popen(argv)
            pid = proc.pid
            note = "spawned"
        except Exception as exc:  # noqa: BLE001
            return {"error": f"spawn failed: {exc}"}
    tracked = process_registry.add(name, argv, pid)
    return {
        "summary": f"{note}: {name} (pid={pid})" if pid else f"{note}: {name}",
        "argv": argv,
        "pid": pid,
        "started_at": tracked.started_at,
    }


@tool(description="Start the simgraph collector (directory watcher).")
async def start_collector() -> dict:
    if process_registry.alive("collector"):
        return {
            "summary": "collector already running",
            "pid": process_registry.procs["collector"].pid,
        }
    return _spawn("collector", ["simgraph", "c"])


@tool(description="Start the simgraph MCP SSE server (reads ./mcp.toml).")
async def start_mcp() -> dict:
    if process_registry.alive("mcp"):
        return {"summary": "mcp already running"}
    return _spawn("mcp", ["simgraph", "mcp"])


@tool(description="Start the embedded post_service MCP server.")
async def start_post_service(host: str = "127.0.0.1", port: int = 8000) -> dict:
    if process_registry.alive("post_service"):
        return {"summary": "post_service already running"}
    return _spawn(
        "post_service",
        ["simgraph", "post-service", "--host", host, "--port", str(port)],
    )


@tool(description="Run `simgraph init` to (re)write the default simgraph.toml.")
async def init_config() -> dict:
    return _spawn("init", ["simgraph", "init"], wait=True)


@tool(description="Return the simgraph CLI version string.")
async def cli_version() -> dict:
    if _real_run() and shutil.which("simgraph") is None:
        return {"error": "simgraph not on PATH"}
    if not _real_run():
        return {"summary": "SimGraph 1.0.0 (dry_run)", "version": "1.0.0"}
    return _spawn("version", ["simgraph", "--version"], wait=True)


@tool(description="Report which simgraph background processes are alive.")
async def cli_status() -> dict:
    return {
        "summary": f"{sum(1 for p in process_registry.procs.values() if p.status == 'running')} running",
        "procs": [
            {"name": p.name, "pid": p.pid, "status": p.status, "argv": p.argv}
            for p in process_registry.procs.values()
        ],
    }


@tool(description="Stop a tracked simgraph subprocess by name.")
async def stop_process(name: str) -> dict:
    p = process_registry.procs.get(name)
    if p is None:
        return {"error": f"no tracked process named {name}"}
    if _real_run() and p.pid:
        try:
            import psutil
            psutil.Process(p.pid).terminate()
        except Exception as exc:  # noqa: BLE001
            return {"error": f"terminate failed: {exc}"}
    p.status = "exited"
    return {"summary": f"stopped {name}", "name": name}


SIM_CLI_TOOLS = [
    start_collector,
    start_mcp,
    start_post_service,
    init_config,
    cli_version,
    cli_status,
    stop_process,
]
