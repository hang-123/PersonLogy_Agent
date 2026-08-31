"""Ports for the P10 immutable record stream."""

from builtins import list as builtins_list
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from personlogy.domain.audit.models import AuditEvent


@dataclass(frozen=True, slots=True)
class ChainVerification:
    valid: bool
    checked_events: int
    failure_reason: str | None = None


class AuditSink(Protocol):
    async def append(self, event: AuditEvent) -> AuditEvent: ...

    async def get(self, event_id: UUID) -> AuditEvent | None: ...

    async def list(
        self,
        *,
        trace_id: str | None = None,
        entity_id: str | None = None,
        event_type: str | None = None,
        limit: int = 100,
    ) -> list[AuditEvent]: ...

    async def list_since(
        self, sequence: int, *, limit: int = 1000
    ) -> builtins_list[AuditEvent]: ...

    async def verify_chain(self) -> ChainVerification: ...


__all__ = ["AuditSink", "ChainVerification"]
