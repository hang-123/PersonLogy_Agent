"""Bounded audit export, archive, and offline verification operations."""

from __future__ import annotations

import gzip
import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from personlogy.domain.audit import AuditEvent
from personlogy.ports.audit import AuditSink, ChainVerification
from personlogy.shared.errors import DomainValidationError

_BATCH_SIZE = 1000


@dataclass(frozen=True, slots=True)
class AuditExportResult:
    path: str
    event_count: int
    first_sequence: int | None
    last_sequence: int | None
    content_sha256: str


@dataclass(frozen=True, slots=True)
class AuditExportVerification:
    path: str
    event_count: int
    content_sha256: str
    chain: ChainVerification


def audit_event_record(event: AuditEvent) -> dict[str, object]:
    """Return the complete non-sensitive JSONL representation of an event."""

    record = event.canonical_fields()
    record.update(
        sequence=event.sequence,
        prev_hash=event.prev_hash,
        event_hash=event.event_hash,
    )
    return record


async def _all_events(sink: AuditSink) -> list[AuditEvent]:
    events: list[AuditEvent] = []
    sequence = 0
    while True:
        batch = await sink.list_since(sequence, limit=_BATCH_SIZE)
        if not batch:
            return events
        events.extend(batch)
        last = batch[-1].sequence
        if last is None or last <= sequence:
            raise DomainValidationError("audit sink returned a non-advancing sequence")
        sequence = last
        if len(batch) < _BATCH_SIZE:
            return events


def _encoded_lines(events: Iterable[AuditEvent]) -> tuple[bytes, int, int | None, int | None]:
    chunks: list[bytes] = []
    count = 0
    first: int | None = None
    last: int | None = None
    for event in events:
        line = (
            json.dumps(
                audit_event_record(event),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            + b"\n"
        )
        chunks.append(line)
        count += 1
        if first is None:
            first = event.sequence
        last = event.sequence
    return b"".join(chunks), count, first, last


def _write(path: Path, content: bytes, *, compressed: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if compressed:
        with gzip.open(path, "wb") as stream:
            stream.write(content)
    else:
        path.write_bytes(content)


async def export_audit(sink: AuditSink, path: str | Path) -> AuditExportResult:
    """Export the complete ordered audit stream as UTF-8 JSONL."""

    events = await _all_events(sink)
    content, count, first, last = _encoded_lines(events)
    target = Path(path)
    _write(target, content, compressed=False)
    return AuditExportResult(
        path=str(target),
        event_count=count,
        first_sequence=first,
        last_sequence=last,
        content_sha256=hashlib.sha256(content).hexdigest(),
    )


async def archive_audit(sink: AuditSink, path: str | Path) -> AuditExportResult:
    """Write a gzip-compressed JSONL archive without deleting live events."""

    events = await _all_events(sink)
    content, count, first, last = _encoded_lines(events)
    target = Path(path)
    _write(target, content, compressed=True)
    return AuditExportResult(
        path=str(target),
        event_count=count,
        first_sequence=first,
        last_sequence=last,
        content_sha256=hashlib.sha256(content).hexdigest(),
    )


def _open_export(path: Path) -> bytes:
    if path.suffix.lower() == ".gz":
        with gzip.open(path, "rb") as stream:
            return stream.read()
    return path.read_bytes()


def _event_from_record(record: dict[str, Any]) -> AuditEvent:
    fields = {
        key: record[key]
        for key in (
            "event_type",
            "schema_version",
            "trace_id",
            "span_id",
            "parent_span_id",
            "request_id",
            "actor_type",
            "actor_id",
            "entity_type",
            "entity_id",
            "status",
            "reason_code",
            "before_digest",
            "after_digest",
            "metadata",
        )
    }
    fields["event_id"] = UUID(str(record["event_id"]))
    fields["occurred_at"] = datetime.fromisoformat(str(record["occurred_at"]))
    fields["sequence"] = int(record["sequence"])
    fields["prev_hash"] = record["prev_hash"]
    fields["event_hash"] = str(record["event_hash"])
    return AuditEvent(**fields)


def verify_audit_export(path: str | Path) -> AuditExportVerification:
    """Verify JSONL event structure and the complete exported hash chain."""

    target = Path(path)
    content = _open_export(target)
    digest = hashlib.sha256(content).hexdigest()
    previous_hash: str | None = None
    checked = 0
    failure: str | None = None
    for line_number, raw_line in enumerate(content.splitlines(), start=1):
        if not raw_line.strip():
            continue
        try:
            parsed = json.loads(raw_line)
            if not isinstance(parsed, dict):
                raise TypeError("record is not an object")
            event = _event_from_record(parsed)
            expected_sequence = checked + 1
            if event.sequence != expected_sequence:
                failure = "audit export sequence is not contiguous"
                break
            if event.prev_hash != previous_hash:
                failure = "audit export previous hash does not match"
                break
            if event.event_hash != event.hash_for(expected_sequence, previous_hash):
                failure = "audit export event hash does not match"
                break
            checked += 1
            previous_hash = event.event_hash
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            failure = f"invalid audit export record at line {line_number}: {error}"
            break
    chain = ChainVerification(
        valid=failure is None,
        checked_events=checked,
        failure_reason=failure,
    )
    return AuditExportVerification(
        path=str(target),
        event_count=checked,
        content_sha256=digest,
        chain=chain,
    )


__all__ = [
    "AuditExportResult",
    "AuditExportVerification",
    "archive_audit",
    "audit_event_record",
    "export_audit",
    "verify_audit_export",
]
