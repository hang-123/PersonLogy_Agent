"""SQLite append-only record store for P10 audit events."""

from __future__ import annotations

import json
import sqlite3
from builtins import list as builtins_list
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import UUID

from personlogy.domain.audit.models import AuditEvent
from personlogy.ports.audit import AuditSink, ChainVerification
from personlogy.shared.errors import DomainValidationError

AUDIT_SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS audit_event (
    event_id TEXT PRIMARY KEY,
    occurred_at TEXT NOT NULL,
    event_type TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    trace_id TEXT NOT NULL,
    span_id TEXT,
    parent_span_id TEXT,
    request_id TEXT,
    actor_type TEXT NOT NULL,
    actor_id TEXT,
    entity_type TEXT NOT NULL,
    entity_id TEXT,
    status TEXT NOT NULL,
    reason_code TEXT,
    before_digest TEXT,
    after_digest TEXT,
    metadata TEXT NOT NULL,
    sequence INTEGER NOT NULL UNIQUE,
    prev_hash TEXT,
    event_hash TEXT NOT NULL UNIQUE
);
CREATE INDEX IF NOT EXISTS audit_event_trace_idx
    ON audit_event(trace_id, sequence);
CREATE INDEX IF NOT EXISTS audit_event_entity_idx
    ON audit_event(entity_type, entity_id, sequence);
CREATE INDEX IF NOT EXISTS audit_event_type_idx
    ON audit_event(event_type, sequence);

CREATE TABLE IF NOT EXISTS audit_chain_head (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    sequence INTEGER NOT NULL,
    event_hash TEXT
);
INSERT OR IGNORE INTO audit_chain_head (id, sequence, event_hash)
VALUES (1, 0, NULL);
"""


def _metadata(value: str) -> dict[str, object]:
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise TypeError("stored audit metadata is not an object")
    return cast(dict[str, object], parsed)


def _ensure_audit_columns(connection: sqlite3.Connection) -> None:
    """Upgrade the first P10 schema before request context was persisted."""
    columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(audit_event)").fetchall()
    }
    if "request_id" not in columns:
        connection.execute("ALTER TABLE audit_event ADD COLUMN request_id TEXT")
    if "before_digest" not in columns:
        connection.execute("ALTER TABLE audit_event ADD COLUMN before_digest TEXT")
    if "after_digest" not in columns:
        connection.execute("ALTER TABLE audit_event ADD COLUMN after_digest TEXT")
    connection.commit()


def _event_from_row(row: sqlite3.Row) -> AuditEvent:
    return AuditEvent(
        event_id=UUID(row["event_id"]),
        occurred_at=datetime.fromisoformat(row["occurred_at"]),
        event_type=row["event_type"],
        schema_version=row["schema_version"],
        trace_id=row["trace_id"],
        span_id=row["span_id"],
        parent_span_id=row["parent_span_id"],
        request_id=row["request_id"],
        actor_type=row["actor_type"],
        actor_id=row["actor_id"],
        entity_type=row["entity_type"],
        entity_id=row["entity_id"],
        status=row["status"],
        reason_code=row["reason_code"],
        before_digest=row["before_digest"],
        after_digest=row["after_digest"],
        metadata=_metadata(row["metadata"]),
        sequence=row["sequence"],
        prev_hash=row["prev_hash"],
        event_hash=row["event_hash"],
    )


class SQLiteRecordStore(AuditSink):
    """Durable append-only audit sink sharing the application's SQLite file."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        connection = self.connect()
        try:
            connection.executescript(AUDIT_SCHEMA)
            _ensure_audit_columns(connection)
        finally:
            connection.close()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    async def append(self, event: AuditEvent) -> AuditEvent:
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing_row = connection.execute(
                "SELECT * FROM audit_event WHERE event_id = ?", (str(event.event_id),)
            ).fetchone()
            if existing_row is not None:
                existing = _event_from_row(existing_row)
                if existing.canonical_json() != event.canonical_json():
                    raise DomainValidationError("event id already exists with different content")
                connection.commit()
                return existing

            head = connection.execute(
                "SELECT sequence, event_hash FROM audit_chain_head WHERE id = 1"
            ).fetchone()
            if head is None:
                raise DomainValidationError("audit chain head is missing")
            sequence = int(head["sequence"]) + 1
            prev_hash = cast(str | None, head["event_hash"])
            event_hash = event.hash_for(sequence, prev_hash)
            connection.execute(
                """INSERT INTO audit_event (
                    event_id, occurred_at, event_type, schema_version, trace_id,
                    span_id, parent_span_id, request_id, actor_type, actor_id, entity_type,
                    entity_id, status, reason_code, before_digest, after_digest, metadata,
                    sequence, prev_hash, event_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(event.event_id),
                    event.occurred_at.astimezone(UTC).isoformat(),
                    event.event_type,
                    event.schema_version,
                    event.trace_id,
                    event.span_id,
                    event.parent_span_id,
                    event.request_id,
                    event.actor_type,
                    event.actor_id,
                    event.entity_type,
                    event.entity_id,
                    event.status,
                    event.reason_code,
                    event.before_digest,
                    event.after_digest,
                    json.dumps(
                        dict(event.metadata),
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                        default=str,
                    ),
                    sequence,
                    prev_hash,
                    event_hash,
                ),
            )
            connection.execute(
                "UPDATE audit_chain_head SET sequence = ?, event_hash = ? WHERE id = 1",
                (sequence, event_hash),
            )
            connection.commit()
            return event.with_integrity(
                sequence=sequence,
                prev_hash=prev_hash,
                event_hash=event_hash,
            )
        except sqlite3.IntegrityError as error:
            connection.rollback()
            raise DomainValidationError("audit event violates append-only constraints") from error
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    async def get(self, event_id: UUID) -> AuditEvent | None:
        connection = self.connect()
        try:
            row = connection.execute(
                "SELECT * FROM audit_event WHERE event_id = ?", (str(event_id),)
            ).fetchone()
            return _event_from_row(row) if row is not None else None
        finally:
            connection.close()

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
        parameters: list[object] = []
        if trace_id is not None:
            filters.append("trace_id = ?")
            parameters.append(trace_id)
        if entity_id is not None:
            filters.append("entity_id = ?")
            parameters.append(entity_id)
        if event_type is not None:
            filters.append("event_type = ?")
            parameters.append(event_type)
        where = f"WHERE {' AND '.join(filters)}" if filters else ""
        connection = self.connect()
        try:
            rows = connection.execute(
                f"SELECT * FROM audit_event {where} ORDER BY sequence ASC LIMIT ?",
                (*parameters, limit),
            ).fetchall()
            return [_event_from_row(row) for row in rows]
        finally:
            connection.close()

    async def list_since(
        self, sequence: int, *, limit: int = 1000
    ) -> builtins_list[AuditEvent]:
        if sequence < 0 or not 1 <= limit <= 5000:
            raise DomainValidationError("audit sequence and query limit are invalid")
        connection = self.connect()
        try:
            rows = connection.execute(
                "SELECT * FROM audit_event WHERE sequence > ? ORDER BY sequence ASC LIMIT ?",
                (sequence, limit),
            ).fetchall()
            return [_event_from_row(row) for row in rows]
        finally:
            connection.close()

    async def verify_chain(self) -> ChainVerification:
        connection = self.connect()
        try:
            rows = connection.execute(
                "SELECT * FROM audit_event ORDER BY sequence ASC"
            ).fetchall()
            previous_hash: str | None = None
            for expected_sequence, row in enumerate(rows, start=1):
                event = _event_from_row(row)
                if event.sequence != expected_sequence:
                    return ChainVerification(
                        valid=False,
                        checked_events=expected_sequence - 1,
                        failure_reason="audit sequence is not contiguous",
                    )
                if event.prev_hash != previous_hash:
                    return ChainVerification(
                        valid=False,
                        checked_events=expected_sequence - 1,
                        failure_reason="audit previous hash does not match",
                    )
                expected_hash = event.hash_for(expected_sequence, previous_hash)
                if event.event_hash != expected_hash:
                    return ChainVerification(
                        valid=False,
                        checked_events=expected_sequence - 1,
                        failure_reason="audit event hash does not match",
                    )
                previous_hash = event.event_hash
            head = connection.execute(
                "SELECT sequence, event_hash FROM audit_chain_head WHERE id = 1"
            ).fetchone()
            if head is None or head["sequence"] != len(rows) or head["event_hash"] != previous_hash:
                return ChainVerification(
                    valid=False,
                    checked_events=len(rows),
                    failure_reason="audit chain head does not match events",
                )
            return ChainVerification(valid=True, checked_events=len(rows))
        finally:
            connection.close()


__all__ = ["SQLiteRecordStore"]
