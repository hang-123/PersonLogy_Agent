import asyncio
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from personlogy.adapters.sqlite_audit import SQLiteRecordStore
from personlogy.domain.audit import AuditEvent
from personlogy.shared.errors import DomainValidationError


def test_sqlite_record_store_appends_and_verifies_hash_chain(tmp_path: Path) -> None:
    asyncio.run(_test_sqlite_record_store_appends_and_verifies_hash_chain(tmp_path))


async def _test_sqlite_record_store_appends_and_verifies_hash_chain(tmp_path: Path) -> None:
    store = SQLiteRecordStore(tmp_path / "personlogy.sqlite3")
    first = AuditEvent(
        event_type="job.started",
        status="started",
        trace_id="trace-1",
        actor_type="system",
        entity_type="job",
        entity_id="job-1",
        occurred_at=datetime(2026, 8, 30, 1, 0, tzinfo=UTC),
        metadata={"job_kind": "pdf.parse"},
    )
    second = AuditEvent(
        event_type="job.failed",
        status="failed",
        trace_id="trace-1",
        actor_type="system",
        entity_type="job",
        entity_id="job-1",
        occurred_at=datetime(2026, 8, 30, 1, 1, tzinfo=UTC),
        reason_code="parser_error",
    )

    stored_first = await store.append(first)
    stored_second = await store.append(second)

    assert stored_first.sequence == 1
    assert stored_second.sequence == 2
    assert stored_second.prev_hash == stored_first.event_hash
    assert (await store.list(trace_id="trace-1")) == [stored_first, stored_second]
    assert await store.verify_chain() == type(await store.verify_chain())(
        valid=True, checked_events=2
    )


def test_sqlite_record_store_append_is_idempotent(tmp_path: Path) -> None:
    asyncio.run(_test_sqlite_record_store_append_is_idempotent(tmp_path))


async def _test_sqlite_record_store_append_is_idempotent(tmp_path: Path) -> None:
    store = SQLiteRecordStore(tmp_path / "personlogy.sqlite3")
    event = AuditEvent(
        event_type="tool.requested",
        status="requested",
        trace_id="trace-2",
        actor_type="user",
        actor_id="user-1",
        entity_type="tool_invocation",
        entity_id="invocation-1",
    )

    first = await store.append(event)
    second = await store.append(event)

    assert second == first
    with sqlite3.connect(tmp_path / "personlogy.sqlite3") as connection:
        assert connection.execute("SELECT COUNT(*) FROM audit_event").fetchone()[0] == 1


def test_sqlite_record_store_rejects_event_id_reuse_with_different_content(
    tmp_path: Path,
) -> None:
    asyncio.run(_test_sqlite_record_store_rejects_event_id_reuse_with_different_content(tmp_path))


async def _test_sqlite_record_store_rejects_event_id_reuse_with_different_content(
    tmp_path: Path,
) -> None:
    store = SQLiteRecordStore(tmp_path / "personlogy.sqlite3")
    event_id = uuid4()
    await store.append(
        AuditEvent(
            event_id=event_id,
            event_type="document.exported",
            status="succeeded",
            trace_id="trace-3",
            actor_type="user",
            entity_type="document",
        )
    )

    with pytest.raises(DomainValidationError, match="different content"):
        await store.append(
            AuditEvent(
                event_id=event_id,
                event_type="document.deleted",
                status="succeeded",
                trace_id="trace-3",
                actor_type="user",
                entity_type="document",
            )
        )


def test_sqlite_record_store_detects_tampering(tmp_path: Path) -> None:
    asyncio.run(_test_sqlite_record_store_detects_tampering(tmp_path))


async def _test_sqlite_record_store_detects_tampering(tmp_path: Path) -> None:
    database = tmp_path / "personlogy.sqlite3"
    store = SQLiteRecordStore(database)
    stored = await store.append(
        AuditEvent(
            event_type="permission.changed",
            status="succeeded",
            trace_id="trace-4",
            actor_type="user",
            entity_type="project",
            entity_id="project-1",
        )
    )

    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE audit_event SET status = 'denied' WHERE event_id = ?",
            (str(stored.event_id),),
        )

    verification = await store.verify_chain()
    assert verification.valid is False
    assert verification.failure_reason == "audit event hash does not match"
