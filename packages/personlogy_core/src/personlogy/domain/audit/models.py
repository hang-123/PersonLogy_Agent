"""Immutable audit event model and canonical hash material."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from hashlib import sha256
from uuid import UUID, uuid4

from personlogy.shared.errors import DomainValidationError

_MAX_METADATA_BYTES = 8192
_MAX_METADATA_DEPTH = 4
_ALLOWED_METADATA_KEYS = frozenset(
    {
        "actor_id_digest",
        "args_digest",
        "attempt",
        "auditor_span_id",
        "author_digest",
        "base_version",
        "build_id",
        "candidate_kind",
        "change_count",
        "compiler_version",
        "decision",
        "document_count",
        "duration_ms",
        "entity_count",
        "embedding_version",
        "error_digest",
        "errors_digest",
        "expand_relations",
        "failure_reason_digest",
        "idempotency_key_digest",
        "index_version",
        "job_kind",
        "kind",
        "limit",
        "model_name",
        "model_version",
        "namespace",
        "output_digest",
        "output_changed",
        "original_output_digest",
        "parent_job_id",
        "parent_trace_id",
        "policy_version",
        "progress",
        "project_id",
        "proposal_id",
        "query_digest",
        "reason_digest",
        "required_checks_digest",
        "result_count",
        "result_digest",
        "replay_job_id",
        "replay_plan_id",
        "retrieval_request_id",
        "retryable",
        "risk_class",
        "risk_level",
        "schema_version",
        "source_version_id",
        "side_effect_digest",
        "stage",
        "target_version",
        "tool_invocation_id",
        "tool_name",
        "tool_version",
        "trace_id",
        "violated_policies_digest",
        "version",
        "difference_dimensions",
        "replay_attempt",
        "replay_output_digest",
    }
)


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def digest_for(value: object) -> str:
    """Return a deterministic digest without retaining the original value."""

    return sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _sanitize_metadata(value: object, *, depth: int = 0) -> object:
    if depth > _MAX_METADATA_DEPTH:
        raise DomainValidationError("audit metadata nesting is too deep")
    if isinstance(value, Mapping):
        sanitized: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str) or key not in _ALLOWED_METADATA_KEYS:
                raise DomainValidationError(
                    f"audit metadata field is not allowed: {key!r}"
                )
            sanitized[key] = _sanitize_metadata(item, depth=depth + 1)
        return sanitized
    if isinstance(value, (list, tuple)):
        return [_sanitize_metadata(item, depth=depth + 1) for item in value]
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    raise DomainValidationError("audit metadata must contain JSON-compatible values")


def sanitize_metadata(metadata: Mapping[str, object]) -> dict[str, object]:
    """Validate and copy the bounded, non-sensitive audit metadata envelope."""

    sanitized = _sanitize_metadata(metadata)
    if not isinstance(sanitized, dict):  # pragma: no cover - guarded by Mapping input
        raise DomainValidationError("audit metadata must be an object")
    encoded = _canonical_json(sanitized).encode("utf-8")
    if len(encoded) > _MAX_METADATA_BYTES:
        raise DomainValidationError("audit metadata exceeds the size limit")
    return sanitized


def _validate_digest(name: str, value: str | None) -> None:
    if value is None:
        return
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise DomainValidationError(f"{name} must be a SHA-256 hexadecimal digest")


@dataclass(frozen=True, slots=True)
class AuditEvent:
    """One immutable semantic fact in the P10 record stream.

    Integrity fields are assigned by the RecordStore. An event is never updated
    in place; a later event must be appended to describe a correction.
    """

    event_type: str
    status: str
    trace_id: str
    actor_type: str
    entity_type: str
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    schema_version: str = "1.0"
    event_id: UUID = field(default_factory=uuid4)
    span_id: str | None = None
    parent_span_id: str | None = None
    request_id: str | None = None
    actor_id: str | None = None
    entity_id: str | None = None
    reason_code: str | None = None
    before_digest: str | None = None
    after_digest: str | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)
    sequence: int | None = None
    prev_hash: str | None = None
    event_hash: str | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "event_type",
            "status",
            "trace_id",
            "actor_type",
            "entity_type",
            "schema_version",
        ):
            value = getattr(self, field_name)
            if not value.strip():
                raise DomainValidationError(f"{field_name} is required")
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise DomainValidationError("occurred_at must be timezone-aware")
        if self.sequence is not None and self.sequence < 1:
            raise DomainValidationError("sequence must be positive")
        if not isinstance(self.metadata, Mapping):
            raise DomainValidationError("metadata must be a mapping")
        _validate_digest("before_digest", self.before_digest)
        _validate_digest("after_digest", self.after_digest)
        object.__setattr__(self, "metadata", sanitize_metadata(self.metadata))

    def canonical_fields(self) -> dict[str, object]:
        """Return the stable event content used for idempotency and hashing."""

        return {
            "event_id": str(self.event_id),
            "occurred_at": self.occurred_at.astimezone(UTC).isoformat(),
            "event_type": self.event_type,
            "schema_version": self.schema_version,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "request_id": self.request_id,
            "actor_type": self.actor_type,
            "actor_id": self.actor_id,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "status": self.status,
            "reason_code": self.reason_code,
            "before_digest": self.before_digest,
            "after_digest": self.after_digest,
            "metadata": dict(self.metadata),
        }

    def canonical_json(self) -> str:
        return _canonical_json(self.canonical_fields())

    def hash_for(self, sequence: int, prev_hash: str | None) -> str:
        if sequence < 1:
            raise DomainValidationError("sequence must be positive")
        material = f"{self.canonical_json()}|{sequence}|{prev_hash or ''}"
        return sha256(material.encode("utf-8")).hexdigest()

    def with_integrity(
        self, *, sequence: int, prev_hash: str | None, event_hash: str
    ) -> AuditEvent:
        return replace(
            self,
            sequence=sequence,
            prev_hash=prev_hash,
            event_hash=event_hash,
        )
