"""Skill loader — Claude-Code-style markdown+frontmatter.

A skill file looks like:

    ---
    name: cfd-loadfile
    description: Inject loadFile workflow guidance
    trigger: always              # or: tool_search
    ---

    When the user asks to inspect a case, ...

The framework only loads and lists skills. *How* the host app uses
them (always-on prompt injection, deferred via tool_search, etc.) is
the host's call.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

import frontmatter


@dataclass
class Skill:
    name: str
    description: str
    body: str
    metadata: dict[str, Any]
    path: Path | None = None

    @property
    def trigger(self) -> str:
        return self.metadata.get("trigger", "always")


class SkillLoader:
    def __init__(self, *roots: str | Path):
        self.roots = [Path(r) for r in roots]

    def discover(self) -> list[Skill]:
        out: list[Skill] = []
        for root in self.roots:
            if not root.exists():
                continue
            for md in sorted(root.rglob("*.md")):
                out.append(self.load(md))
        return out

    def load(self, path: str | Path) -> Skill:
        p = Path(path)
        post = frontmatter.load(str(p))
        meta = dict(post.metadata or {})
        return Skill(
            name=meta.get("name") or p.stem,
            description=meta.get("description", ""),
            body=post.content.strip(),
            metadata=meta,
            path=p,
        )

    def __iter__(self) -> Iterator[Skill]:
        return iter(self.discover())
