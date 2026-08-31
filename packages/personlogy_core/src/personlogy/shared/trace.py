"""Async-safe trace context with explicit cross-process serialization."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from uuid import uuid4

_CURRENT_TRACE: ContextVar[TraceContext | None] = ContextVar(
    "personlogy_trace_context", default=None
)


@dataclass(frozen=True, slots=True)
class TraceContext:
    trace_id: str
    span_id: str
    request_id: str | None = None
    parent_span_id: str | None = None
    actor_type: str = "system"
    actor_id: str | None = None

    def __post_init__(self) -> None:
        for name in ("trace_id", "span_id", "actor_type"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} is required")

    @classmethod
    def root(
        cls,
        *,
        request_id: str | None = None,
        actor_type: str = "system",
        actor_id: str | None = None,
    ) -> TraceContext:
        return cls(
            trace_id=cls.new_id("trace"),
            span_id=cls.new_id("span"),
            request_id=request_id,
            actor_type=actor_type,
            actor_id=actor_id,
        )

    @classmethod
    def current(cls) -> TraceContext | None:
        return _CURRENT_TRACE.get()

    @classmethod
    def current_or_root(cls) -> TraceContext:
        return cls.current() or cls.root()

    @classmethod
    def from_job(
        cls,
        *,
        trace_id: str,
        span_id: str | None,
        parent_span_id: str | None,
        request_id: str | None,
    ) -> TraceContext:
        return cls(
            trace_id=trace_id,
            span_id=span_id or cls.new_id("span"),
            parent_span_id=parent_span_id,
            request_id=request_id,
        )

    @classmethod
    def new_id(cls, prefix: str) -> str:
        return f"{prefix}-{uuid4().hex}"

    def child(self) -> TraceContext:
        return TraceContext(
            trace_id=self.trace_id,
            span_id=self.new_id("span"),
            parent_span_id=self.span_id,
            request_id=self.request_id,
            actor_type=self.actor_type,
            actor_id=self.actor_id,
        )

    def as_dict(self) -> dict[str, str | None]:
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "request_id": self.request_id,
            "actor_type": self.actor_type,
            "actor_id": self.actor_id,
        }

    @contextmanager
    def activate(self) -> Iterator[TraceContext]:
        token: Token[TraceContext | None] = _CURRENT_TRACE.set(self)
        try:
            yield self
        finally:
            _CURRENT_TRACE.reset(token)


__all__ = ["TraceContext"]
