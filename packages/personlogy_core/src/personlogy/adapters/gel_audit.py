"""Gel append-only persistence adapter for the P10 audit stream."""

from __future__ import annotations

import json
from builtins import list as builtins_list
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from gel import errors as gel_errors

from personlogy.domain.audit.models import AuditEvent
from personlogy.ports.audit import AuditSink, ChainVerification
from personlogy.shared.errors import DomainValidationError

__all__ = ["GelAuditStore"]


def _json(value: dict[str, object]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _metadata(value: object) -> dict[str, object]:
    parsed = json.loads(value) if isinstance(value, str) else value
    if not isinstance(parsed, dict):
        raise ValueError("stored audit metadata is not an object")
    return cast(dict[str, object], parsed)


def _project_id(metadata: dict[str, object]) -> UUID | None:
    value = metadata.get("project_id")
    if value is None:
        return None
    try:
        return UUID(str(value))
    except ValueError as error:
        raise DomainValidationError("audit metadata project_id must be a UUID") from error


def _event_from_row(row: Any) -> AuditEvent:
    return AuditEvent(
        event_id=cast(UUID, row.id),
        occurred_at=cast(datetime, row.created_at),
        event_type=cast(str, row.event_type),
        schema_version=cast(str, row.schema_version),
        trace_id=cast(str, row.trace_id),
        span_id=cast(str | None, row.span_id),
        parent_span_id=cast(str | None, row.parent_span_id),
        request_id=cast(str | None, row.request_id),
        actor_type=cast(str, row.actor_type),
        actor_id=cast(str | None, row.actor_id),
        entity_type=cast(str, row.entity_type),
        entity_id=cast(str | None, row.entity_id),
        status=cast(str, row.status),
        reason_code=cast(str | None, row.reason_code),
        before_digest=cast(str | None, row.before_digest),
        after_digest=cast(str | None, row.after_digest),
        metadata=_metadata(row.metadata),
        sequence=int(row.sequence),
        prev_hash=cast(str | None, row.prev_hash),
        event_hash=cast(str, row.event_hash),
    )


class GelAuditStore(AuditSink):
    """Durable Gel audit sink with an atomic global hash-chain head.

    A short transaction is opened per append. The domain event id is used as
    Gel's object id, so retrying the same event is idempotent while a different
    payload for that id is rejected.
    """

    _SHAPE = """{
      id, created_at, event_type, schema_version, trace_id, span_id,
      parent_span_id, request_id, actor_type, actor_id, entity_type,
      entity_id, status, reason_code, before_digest, after_digest, project_id,
      metadata, sequence, prev_hash, event_hash,
    }"""

    def __init__(self, store: Any) -> None:
        self._store = store

    async def _transaction(self, operation: Any) -> Any:
        retry: Any = self._store.client.transaction()
        tx = await retry.__anext__()
        entered = False
        try:
            await tx.__aenter__()
            entered = True
            result = await operation(tx)
        except BaseException as error:
            if entered:
                await tx.__aexit__(type(error), error, error.__traceback__)
            raise
        else:
            await tx.__aexit__(None, None, None)
            return result

    async def _ensure_head(self, tx: Any) -> Any:
        head = await tx.query_single(
            "select AuditChainHead { sequence, event_hash } filter .key = 'global' limit 1"
        )
        if head is None:
            await tx.execute(
                """
                insert AuditChainHead {
                  key := 'global', sequence := <int64>0,
                  event_hash := <optional str>{}
                }
                unless conflict on .key
                """
            )
            head = await tx.query_single(
                "select AuditChainHead { sequence, event_hash } filter .key = 'global' limit 1"
            )
        if head is None:
            raise DomainValidationError("Gel audit chain head is missing")
        return head

    async def append(self, event: AuditEvent) -> AuditEvent:
        async def operation(tx: Any) -> AuditEvent:
            existing_row = await tx.query_single(
                f"select AuditEvent {self._SHAPE} filter .id = <uuid>$event_id limit 1",
                event_id=event.event_id,
            )
            if existing_row is not None:
                existing = _event_from_row(existing_row)
                if existing.canonical_json() != event.canonical_json():
                    raise DomainValidationError("event id already exists with different content")
                return existing

            head = await self._ensure_head(tx)
            sequence = int(head.sequence) + 1
            prev_hash = cast(str | None, head.event_hash)
            event_hash = event.hash_for(sequence, prev_hash)
            metadata = dict(event.metadata)
            await tx.execute(
                """
                insert AuditEvent {
                  id := <uuid>$event_id,
                  event_type := <str>$event_type,
                  schema_version := <str>$schema_version,
                  trace_id := <str>$trace_id,
                  span_id := <optional str>$span_id,
                  parent_span_id := <optional str>$parent_span_id,
                  request_id := <optional str>$request_id,
                  actor_type := <str>$actor_type,
                  actor_id := <optional str>$actor_id,
                  entity_type := <str>$entity_type,
                  entity_id := <optional str>$entity_id,
                  status := <str>$status,
                  reason_code := <optional str>$reason_code,
                  before_digest := <optional str>$before_digest,
                  after_digest := <optional str>$after_digest,
                  project_id := <optional uuid>$project_id,
                  metadata := <json>$metadata,
                  sequence := <int64>$sequence,
                  prev_hash := <optional str>$prev_hash,
                  event_hash := <str>$event_hash,
                  created_at := <datetime>$occurred_at,
                }
                """,
                event_id=event.event_id,
                event_type=event.event_type,
                schema_version=event.schema_version,
                trace_id=event.trace_id,
                span_id=event.span_id,
                parent_span_id=event.parent_span_id,
                request_id=event.request_id,
                actor_type=event.actor_type,
                actor_id=event.actor_id,
                entity_type=event.entity_type,
                entity_id=event.entity_id,
                status=event.status,
                reason_code=event.reason_code,
                before_digest=event.before_digest,
                after_digest=event.after_digest,
                project_id=_project_id(metadata),
                metadata=_json(metadata),
                sequence=sequence,
                prev_hash=prev_hash,
                event_hash=event_hash,
                occurred_at=event.occurred_at.astimezone(UTC),
            )
            await tx.execute(
                """
                update AuditChainHead
                filter .key = 'global'
                set { sequence := <int64>$sequence, event_hash := <str>$event_hash }
                """,
                sequence=sequence,
                event_hash=event_hash,
            )
            return event.with_integrity(
                sequence=sequence, prev_hash=prev_hash, event_hash=event_hash
            )

        try:
            return cast(AuditEvent, await self._transaction(operation))
        except gel_errors.EdgeDBError as error:
            raise DomainValidationError(
                "Gel audit event violates append-only constraints"
            ) from error

    async def get(self, event_id: UUID) -> AuditEvent | None:
        row = await self._store.client.query_single(
            f"select AuditEvent {self._SHAPE} filter .id = <uuid>$event_id limit 1",
            event_id=event_id,
        )
        return _event_from_row(row) if row is not None else None

    async def list(
        self,
        *,
        trace_id: str | None = None,
        entity_id: str | None = None,
        event_type: str | None = None,
        limit: int = 100,
    ) -> list[AuditEvent]:
        if not 1 <= limit <= 1000:
            raise DomainValidationError("audit query limit must be between 1 and 1000")
        filters: list[str] = []
        values: dict[str, object] = {"limit": limit}
        if trace_id is not None:
            filters.append(".trace_id = <str>$trace_id")
            values["trace_id"] = trace_id
        if entity_id is not None:
            filters.append(".entity_id = <str>$entity_id")
            values["entity_id"] = entity_id
        if event_type is not None:
            filters.append(".event_type = <str>$event_type")
            values["event_type"] = event_type
        predicate = f" filter {' and '.join(filters)}" if filters else ""
        rows = await self._store.client.query(
            f"select AuditEvent {self._SHAPE}{predicate} "
            "order by .sequence asc limit <int64>$limit",
            **values,
        )
        return [_event_from_row(row) for row in rows]

    async def list_since(
        self, sequence: int, *, limit: int = 1000
    ) -> builtins_list[AuditEvent]:
        if sequence < 0 or not 1 <= limit <= 5000:
            raise DomainValidationError("audit sequence and query limit are invalid")
        rows = await self._store.client.query(
            f"""select AuditEvent {self._SHAPE}
                filter .sequence > <int64>$sequence
                order by .sequence asc limit <int64>$limit""",
            sequence=sequence,
            limit=limit,
        )
        return [_event_from_row(row) for row in rows]

    async def verify_chain(self) -> ChainVerification:
        rows = await self._store.client.query(
            f"select AuditEvent {self._SHAPE} order by .sequence asc"
        )
        previous_hash: str | None = None
        for expected_sequence, row in enumerate(rows, start=1):
            event = _event_from_row(row)
            if event.sequence != expected_sequence:
                return ChainVerification(
                    False, expected_sequence - 1, "audit sequence is not contiguous"
                )
            if event.prev_hash != previous_hash:
                return ChainVerification(
                    False, expected_sequence - 1, "audit previous hash does not match"
                )
            if event.event_hash != event.hash_for(expected_sequence, previous_hash):
                return ChainVerification(
                    False, expected_sequence - 1, "audit event hash does not match"
                )
            previous_hash = event.event_hash
        head = await self._store.client.query_single(
            "select AuditChainHead { sequence, event_hash } filter .key = 'global' limit 1"
        )
        if head is None or int(head.sequence) != len(rows) or head.event_hash != previous_hash:
            return ChainVerification(False, len(rows), "audit chain head does not match events")
        return ChainVerification(True, len(rows))
