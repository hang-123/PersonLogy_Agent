"""Governance, issue, duplicate, conflict, and review task models."""

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from personlogy.shared.errors import DomainValidationError, InvalidStateTransitionError


class GovernanceRunStatus(StrEnum):
    PASSED = "passed"
    NEEDS_REVIEW = "needs_review"
    REJECTED = "rejected"


class GovernanceIssueSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class CandidateKind(StrEnum):
    NODE = "node"
    CLAIM = "claim"
    RELATION = "relation"


class ReviewTaskStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    REVISED = "revised"


@dataclass(frozen=True, slots=True)
class GovernanceRun:
    project_id: UUID
    task_id: UUID
    rule_version: str
    status: GovernanceRunStatus
    candidate_ids: tuple[UUID, ...]
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not self.rule_version.strip() or not self.candidate_ids:
            raise DomainValidationError("governance rule version and candidates are required")


@dataclass(frozen=True, slots=True)
class GovernanceIssue:
    run_id: UUID
    candidate_id: UUID
    candidate_kind: CandidateKind
    code: str
    message: str
    severity: GovernanceIssueSeverity
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not self.code.strip() or not self.message.strip():
            raise DomainValidationError("governance issue code and message are required")


@dataclass(frozen=True, slots=True)
class DuplicateGroup:
    project_id: UUID
    candidate_ids: tuple[UUID, ...]
    basis: str
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if len(self.candidate_ids) < 2 or not self.basis.strip():
            raise DomainValidationError("duplicate group needs two candidates and a basis")


@dataclass(frozen=True, slots=True)
class ConflictRecord:
    project_id: UUID
    candidate_ids: tuple[UUID, ...]
    basis: str
    id: UUID = field(default_factory=uuid4)
    status: str = "open"
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if len(self.candidate_ids) < 2 or not self.basis.strip():
            raise DomainValidationError("conflict record needs two candidates and a basis")


@dataclass(frozen=True, slots=True)
class ReviewTask:
    run_id: UUID
    candidate_id: UUID
    candidate_kind: CandidateKind
    status: ReviewTaskStatus = ReviewTaskStatus.PENDING
    reviewer_id: str | None = None
    reason: str | None = None
    before: dict[str, object] = field(default_factory=dict)
    after: dict[str, object] = field(default_factory=dict)
    version: int = 1
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    reviewed_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.version < 1:
            raise DomainValidationError("review task version must be positive")

    def decide(
        self,
        decision: ReviewTaskStatus,
        *,
        reviewer_id: str,
        reason: str,
        after: dict[str, object] | None = None,
        now: datetime | None = None,
    ) -> "ReviewTask":
        if self.status is not ReviewTaskStatus.PENDING:
            raise InvalidStateTransitionError("review task has already been decided")
        if decision is ReviewTaskStatus.PENDING:
            raise DomainValidationError("review decision is required")
        if not reviewer_id.strip() or not reason.strip():
            raise DomainValidationError("reviewer and reason are required")
        return replace(
            self,
            status=decision,
            reviewer_id=reviewer_id,
            reason=reason,
            after=after or {},
            version=self.version + 1,
            reviewed_at=now or datetime.now(UTC),
        )
