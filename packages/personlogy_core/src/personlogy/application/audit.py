"""Shared application helper for constructing immutable audit facts."""

from __future__ import annotations

from collections.abc import Mapping

from personlogy.domain.audit import AuditEvent, digest_for
from personlogy.ports.audit import AuditSink
from personlogy.shared.trace import TraceContext


async def append_audit_event(
    audit_sink: AuditSink | None,
    *,
    event_type: str,
    status: str,
    entity_type: str,
    entity_id: str,
    before: object | None = None,
    after: object | None = None,
    context: TraceContext | None = None,
    reason_code: str | None = None,
    metadata: Mapping[str, object] | None = None,
) -> AuditEvent | None:
    if audit_sink is None:
        return None
    active = context or TraceContext.current_or_root()
    return await audit_sink.append(
        AuditEvent(
            event_type=event_type,
            status=status,
            trace_id=active.trace_id,
            span_id=active.span_id,
            parent_span_id=active.parent_span_id,
            request_id=active.request_id,
            actor_type=active.actor_type,
            actor_id=active.actor_id,
            entity_type=entity_type,
            entity_id=entity_id,
            reason_code=reason_code,
            before_digest=digest_for(before) if before is not None else None,
            after_digest=digest_for(after) if after is not None else None,
            metadata=metadata or {},
        )
    )


__all__ = ["append_audit_event"]
