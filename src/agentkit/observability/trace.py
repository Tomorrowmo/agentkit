"""Tracer — tool/LLM call timing and outcome capture.

In-memory by default. Replaceable: host can subclass and forward to
OTLP / Jaeger / whatever. Span is a context manager; on exit it records
elapsed time and any error.
"""

from __future__ import annotations

import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator


@dataclass
class Span:
    id: str
    kind: str
    started_at: float
    fields: dict[str, Any] = field(default_factory=dict)
    ended_at: float | None = None
    error: str | None = None
    result_meta: dict[str, Any] = field(default_factory=dict)

    @property
    def elapsed_ms(self) -> float | None:
        if self.ended_at is None:
            return None
        return (self.ended_at - self.started_at) * 1000.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "elapsed_ms": self.elapsed_ms,
            "error": self.error,
            "fields": self.fields,
            "result_meta": self.result_meta,
        }


class Tracer:
    def __init__(self) -> None:
        self.spans: list[Span] = []

    @contextmanager
    def span(self, kind: str, **fields: Any) -> Iterator[Span]:
        span = Span(id=uuid.uuid4().hex, kind=kind, started_at=time.time(), fields=fields)
        try:
            yield span
        finally:
            span.ended_at = time.time()
            self.spans.append(span)
            self.on_span(span)

    def on_span(self, span: Span) -> None:
        """Hook: override to forward elsewhere."""
