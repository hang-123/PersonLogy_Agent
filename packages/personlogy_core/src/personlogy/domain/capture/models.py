"""Immutable raw evidence models for the Capture Inbox."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from types import MappingProxyType
from uuid import UUID, uuid4

from personlogy.shared.errors import DomainValidationError


class CaptureResultStatus(StrEnum):
    ACCEPTED = "accepted"
    ALREADY_RECEIVED = "already_received"
    CONFLICT = "conflict"
    REJECTED = "rejected"
    RETRYABLE = "retryable"


@dataclass(frozen=True, slots=True)
class CaptureSourceIdentity:
    source_kind: str
    source_scope: str
    session_key: str
    source_item_key: str
    source_revision: int = 0

    def __post_init__(self) -> None:
        if not all(
            value.strip()
            for value in (
                self.source_kind,
                self.source_scope,
                self.session_key,
                self.source_item_key,
            )
        ):
            raise DomainValidationError("capture source identity fields are required")
        if self.source_revision < 0:
            raise DomainValidationError("capture source revision cannot be negative")


@dataclass(frozen=True, slots=True)
class CapturedEvent:
    schema_version: int
    event_id: UUID
    producer_id: str
    stream_id: str
    sequence: int
    source_identity: CaptureSourceIdentity
    captured_at: datetime
    rule_version: str
    payload_hash: str
    payload: Mapping[str, object]
    occurred_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise DomainValidationError("unsupported capture schema version")
        if not self.producer_id.strip() or not self.stream_id.strip():
            raise DomainValidationError("capture producer and stream are required")
        if self.sequence < 1:
            raise DomainValidationError("capture sequence must be positive")
        if not self.rule_version.strip():
            raise DomainValidationError("capture rule version is required")
        if len(self.payload_hash) != 64:
            raise DomainValidationError("capture payload hash must be a SHA-256 digest")
        try:
            int(self.payload_hash, 16)
        except ValueError as error:
            raise DomainValidationError("capture payload hash must be hexadecimal") from error
        object.__setattr__(self, "payload_hash", self.payload_hash.lower())
        for name, value in (
            ("captured_at", self.captured_at),
            ("created_at", self.created_at),
            ("occurred_at", self.occurred_at),
        ):
            if value is not None and (value.tzinfo is None or value.utcoffset() is None):
                raise DomainValidationError(f"capture {name} must be timezone-aware")
        if not isinstance(self.payload, Mapping):
            raise DomainValidationError("capture payload must be an object")
        # A frozen dataclass alone does not freeze a nested dict. Keep the raw
        # evidence immutable at the domain boundary as well.
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))


@dataclass(frozen=True, slots=True)
class StreamState:
    producer_id: str
    stream_id: str
    next_sequence: int = 1
    last_contiguous_received_sequence: int = 0
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not self.producer_id.strip() or not self.stream_id.strip():
            raise DomainValidationError("capture stream identity is required")
        if self.next_sequence < 1 or self.last_contiguous_received_sequence < 0:
            raise DomainValidationError("capture stream state is invalid")
        if self.updated_at.tzinfo is None or self.updated_at.utcoffset() is None:
            raise DomainValidationError("capture stream timestamp must be timezone-aware")


@dataclass(frozen=True, slots=True)
class CaptureConflict:
    source_identity: CaptureSourceIdentity
    existing_event_id: UUID
    existing_payload_hash: str
    incoming_event_id: UUID
    incoming_payload_hash: str
    reason: str
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not self.reason.strip():
            raise DomainValidationError("capture conflict reason is required")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise DomainValidationError("capture conflict timestamp must be timezone-aware")


@dataclass(frozen=True, slots=True)
class CaptureEventResult:
    event_id: UUID
    status: CaptureResultStatus
    server_receipt_id: str | None = None
    error_code: str | None = None
    error_summary: str | None = None
    job_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class CaptureReceipt:
    results: tuple[CaptureEventResult, ...]
    receipt_id: UUID = field(default_factory=uuid4)
