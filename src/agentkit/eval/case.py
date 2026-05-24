"""EvalCase — the unit of agent behavior validation.

Mirrors the simgraph eval format (前置 / 用户输入 / 期望执行逻辑 /
期望输出 / 反模式 / 证据) in a machine-readable shape.

Two file formats supported:
  - YAML  (preferred for evals — structured)
  - Markdown with frontmatter (preferred for human-curated cases)

Loading is decoupled from execution. Runner takes a list of EvalCase.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import yaml


# A matcher dict says how to compare actual call.arguments to expected.
# Special keys:
#   __any__      : true → field present, value irrelevant
#   __regex__    : value is a regex tested against str(field)
#   __contains__ : value must be `in` the field
# Otherwise: literal equality.
MatcherDict = dict[str, Any]


@dataclass
class ExpectedCall:
    name: str
    args: MatcherDict = field(default_factory=dict)
    optional: bool = False    # if True, OK to skip; otherwise must appear


@dataclass
class EvalCase:
    """One scenario. All fields except id/input are optional."""

    id: str
    user_input: str
    description: str = ""
    setup: dict[str, Any] = field(default_factory=dict)
    # Expected tool_calls in order. Out-of-order failure unless `loose_order=True`.
    expected_calls: list[ExpectedCall] = field(default_factory=list)
    loose_order: bool = False
    # Expected substrings in the final assistant text.
    expected_text_includes: list[str] = field(default_factory=list)
    # Tools that must NOT be called.
    forbidden_calls: list[str] = field(default_factory=list)
    # Substrings that must NOT appear in assistant text.
    forbidden_text_includes: list[str] = field(default_factory=list)
    # For traceability — session id / ticket / link to original evidence.
    evidence: str = ""
    # Free-form tag the host can use to gate runs by category.
    tags: list[str] = field(default_factory=list)


def load_cases(path: str | Path) -> list[EvalCase]:
    """Load cases from a YAML file (list of dicts) or directory of YAMLs."""
    p = Path(path)
    if p.is_dir():
        out: list[EvalCase] = []
        for f in sorted(p.glob("*.yaml")) + sorted(p.glob("*.yml")):
            out.extend(load_cases(f))
        return out

    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or []
    if isinstance(raw, dict):
        raw = [raw]
    return [_from_dict(d) for d in raw]


def _from_dict(d: dict) -> EvalCase:
    return EvalCase(
        id=str(d["id"]),
        user_input=d["user_input"],
        description=d.get("description", ""),
        setup=d.get("setup") or {},
        expected_calls=[_call_from_dict(c) for c in (d.get("expected_calls") or [])],
        loose_order=bool(d.get("loose_order", False)),
        expected_text_includes=list(d.get("expected_text_includes") or []),
        forbidden_calls=list(d.get("forbidden_calls") or []),
        forbidden_text_includes=list(d.get("forbidden_text_includes") or []),
        evidence=str(d.get("evidence", "")),
        tags=list(d.get("tags") or []),
    )


def _call_from_dict(c: dict | str) -> ExpectedCall:
    if isinstance(c, str):
        return ExpectedCall(name=c)
    return ExpectedCall(
        name=c["name"],
        args=c.get("args") or {},
        optional=bool(c.get("optional", False)),
    )


def match_args(expected: MatcherDict, actual: dict[str, Any]) -> tuple[bool, str]:
    """Return (matched, reason). Uses special __any__/__regex__/__contains__ keys."""
    for key, want in expected.items():
        if key not in actual:
            return False, f"missing key: {key}"
        got = actual[key]
        if isinstance(want, dict):
            if "__any__" in want:
                continue
            if "__regex__" in want:
                if not re.search(want["__regex__"], str(got)):
                    return False, f"{key} did not match regex {want['__regex__']!r}: {got!r}"
                continue
            if "__contains__" in want:
                needle = want["__contains__"]
                hay = got if isinstance(got, (list, str, tuple)) else json.dumps(got)
                if needle not in hay:
                    return False, f"{key} does not contain {needle!r}: {got!r}"
                continue
        if got != want:
            return False, f"{key}: expected {want!r}, got {got!r}"
    return True, "ok"
