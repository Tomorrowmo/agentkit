"""Structured JSONL log of agent activity.

One line per event. Append-only. Designed to be `jq`-able offline so
you can answer "which tool calls failed today" or "how long did the
LLM step take" without a database.

The framework writes plumbing events (tool_call, tool_result, llm_call).
Hosts can write whatever else they want — `log.write({...})`.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from threading import Lock
from typing import Any


class InsightLog:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    def write(self, event: dict[str, Any]) -> None:
        record = {"ts": time.time(), **event}
        line = json.dumps(record, ensure_ascii=False, default=str)
        with self._lock, self.path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
