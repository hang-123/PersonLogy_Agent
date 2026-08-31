"""Controlled writeback and publication lifecycle models."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from personlogy.domain.governance.models import CandidateKind
from personlogy.domain.knowledge.models import VerificationStatus
from personlogy.shared.errors import DomainValidationError, InvalidStateTransitionError


class WritebackStatus(StrEnum):
    EFFECTS_PENDING = "effects_pending"
    RETRYABLE_FAILED = "retryable_failed"
    COMPLETED = "completed"
    REVERTED = "reverted"


@dataclass(frozen=True, slots=True)
class CandidateRef:
    candidate_id: UUID
    candidate_kind: CandidateKind
    expected_review_version: int | None = None

    def __post_init__(self) -> None:
        if self.expected_review_version is not None and self.expected_review_version < 1:
            raise DomainValidationError("expected review version must be positive")


@dataclass(frozen=True, slots=True)
class WritebackItem:
    record_id: UUID
    candidate_id: UUID
    candidate_kind: CandidateKind
    before_status: VerificationStatus
    after_status: VerificationStatus
    before_digest: str
    after_digest: str
    result: str = "published"
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not self.before_digest or not self.after_digest:
            raise DomainValidationError("writeback item digests are required")
        if not self.result.strip():
            raise DomainValidationError("writeback item result is required")


@dataclass(frozen=True, slots=True)
class WritebackRecord:
    project_id: UUID
    governance_run_id: UUID
    schema_namespace: str
    schema_version: int
    idempotency_key: str
    request_digest: str
    candidate_digest: str
    candidates: tuple[CandidateRef, ...]
    status: WritebackStatus = WritebackStatus.EFFECTS_PENDING
    effects_job_id: UUID | None = None
    okf_object_key: str | None = None
    index_job_id: UUID | None = None
    error_code: str | None = None
    error_digest: str | None = None
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    committed_at: datetime | None = None
    completed_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.schema_namespace.strip() or self.schema_version < 1:
            raise DomainValidationError("writeback schema namespace and version are required")
        if not self.idempotency_key.strip() or not self.request_digest:
            raise DomainValidationError("writeback idempotency key and request digest are required")
        if not self.candidate_digest or not self.candidates:
            raise DomainValidationError("writeback candidates are required")

    def complete(
        self,
        *,
        okf_object_key: str,
        index_job_id: UUID | None,
        now: datetime | None = None,
    ) -> WritebackRecord:
        if self.status is WritebackStatus.REVERTED:
            raise InvalidStateTransitionError("reverted writeback cannot be completed")
        if not okf_object_key.strip():
            raise DomainValidationError("writeback OKF object key is required")
        return replace(
            self,
            status=WritebackStatus.COMPLETED,
            okf_object_key=okf_object_key,
            index_job_id=index_job_id,
            completed_at=now or datetime.now(UTC),
            error_code=None,
            error_digest=None,
        )

    def fail_retryably(self, *, error_code: str, error_digest: str) -> WritebackRecord:
        if self.status is WritebackStatus.REVERTED:
            raise InvalidStateTransitionError("reverted writeback cannot fail")
        return replace(
            self,
            status=WritebackStatus.RETRYABLE_FAILED,
            error_code=error_code,
            error_digest=error_digest,
        )

    def revert(self, *, now: datetime | None = None) -> WritebackRecord:
        if self.status is not WritebackStatus.COMPLETED:
            raise InvalidStateTransitionError("only a completed writeback can be reverted")
        return replace(self, status=WritebackStatus.REVERTED, completed_at=now or datetime.now(UTC))
