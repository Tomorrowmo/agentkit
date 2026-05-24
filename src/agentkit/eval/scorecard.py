"""Scorecard — aggregate CaseResult into reports.

Produces:
  - JSON summary (machine, for CI gates)
  - Markdown table (human, for PR comments)
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Iterable

from agentkit.eval.runner import CaseResult


class Scorecard:
    def __init__(self, results: Iterable[CaseResult]):
        self.results = list(results)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def failed(self) -> int:
        return self.total - self.passed

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 1.0

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "pass_rate": round(self.pass_rate, 4),
            "results": [
                {
                    "case_id": r.case_id,
                    "passed": r.passed,
                    "reasons": r.reasons,
                    "observed_calls": [
                        {"name": o.name, "arguments": o.arguments, "error": o.error}
                        for o in r.observed_calls
                    ],
                    "observed_text": r.observed_text[:500],
                }
                for r in self.results
            ],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent, default=str)

    def to_markdown(self, title: str = "Eval Scorecard") -> str:
        lines = [
            f"# {title}",
            "",
            f"**{self.passed}/{self.total} passed** ({self.pass_rate:.0%})",
            "",
            "| Case | Status | Reason |",
            "|---|---|---|",
        ]
        for r in self.results:
            status = "✅" if r.passed else "❌"
            reason = "; ".join(r.reasons) or "—"
            lines.append(f"| `{r.case_id}` | {status} | {reason} |")
        return "\n".join(lines)

    def write(self, json_path: str | Path | None = None, md_path: str | Path | None = None) -> None:
        if json_path:
            Path(json_path).write_text(self.to_json(), encoding="utf-8")
        if md_path:
            Path(md_path).write_text(self.to_markdown(), encoding="utf-8")
