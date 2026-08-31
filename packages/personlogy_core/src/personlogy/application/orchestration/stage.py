"""Uniform execution wrapper for auditable long-running stages."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from hashlib import sha256
from time import monotonic
from typing import TypeVar

from personlogy.domain.audit import AuditEvent
from personlogy.domain.job import Job
from personlogy.ports.audit import AuditSink
from personlogy.shared.trace import TraceContext

ResultT = TypeVar("ResultT")
StageOperation = Callable[[], Awaitable[ResultT]]


class StageRunner:
    """Run a stage inside a child span and record its complete lifecycle."""

    def __init__(self, audit_sink: AuditSink | None = None) -> None:
        self._audit_sink = audit_sink

    async def run(
        self,
        *,
        stage: str,
        job: Job,
        operation: StageOperation[ResultT],
        metadata: dict[str, object] | None = None,
    ) -> ResultT:
        if not stage.strip():
            raise ValueError("stage is required")
        parent = TraceContext.current() or TraceContext.from_job(
            trace_id=job.trace_id,
            span_id=job.span_id,
            parent_span_id=job.parent_span_id,
            request_id=job.request_id,
        )
        context = parent.child()
        started_at = monotonic()
        base_metadata = {
            "stage": stage,
            "job_kind": job.kind,
            "attempt": job.attempt,
            **(metadata or {}),
        }
        await self._append(
            "stage.started",
            job,
            context=context,
            metadata=base_metadata,
        )
        try:
            with context.activate():
                result = await operation()
        except Exception as error:
            await self._append(
                "stage.failed",
                job,
                context=context,
                status="failed",
                reason_code="stage_failure",
                metadata={
                    **base_metadata,
                    "duration_ms": round((monotonic() - started_at) * 1000, 2),
                    "error_digest": self._digest(str(error)),
                },
            )
            raise
        await self._append(
            "stage.succeeded",
            job,
            context=context,
            status="succeeded",
            metadata={
                **base_metadata,
                "duration_ms": round((monotonic() - started_at) * 1000, 2),
            },
        )
        return result

    async def _append(
        self,
        event_type: str,
        job: Job,
        *,
        context: TraceContext,
        status: str = "started",
        reason_code: str | None = None,
        metadata: dict[str, object],
    ) -> None:
        if self._audit_sink is None:
            return
        await self._audit_sink.append(
            AuditEvent(
                event_type=event_type,
                status=status,
                trace_id=job.trace_id,
                span_id=context.span_id,
                parent_span_id=context.parent_span_id,
                request_id=job.request_id,
                actor_type=context.actor_type,
                actor_id=context.actor_id,
                entity_type="job_stage",
                entity_id=f"{job.id}:{job.attempt}:{metadata['stage']}",
                reason_code=reason_code,
                metadata=metadata,
            )
        )

    @staticmethod
    def _digest(value: str) -> str:
        return sha256(value.encode("utf-8")).hexdigest()


__all__ = ["StageOperation", "StageRunner"]
