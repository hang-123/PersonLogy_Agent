from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from uuid import UUID, uuid4

from personlogy.shared.errors import DomainValidationError, InvalidStateTransitionError


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    RETRYING = "retrying"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_JOB_STATUSES = frozenset({JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED})


@dataclass(frozen=True, slots=True)
class Job:
    kind: str
    idempotency_key: str
    payload: dict[str, object]
    max_attempts: int = 3
    timeout_seconds: int = 900
    id: UUID = field(default_factory=uuid4)
    trace_id: str = field(default_factory=lambda: f"job-{uuid4().hex}")
    request_id: str | None = None
    span_id: str | None = None
    parent_span_id: str | None = None
    status: JobStatus = JobStatus.QUEUED
    progress: int = 0
    stage: str = "queued"
    attempt: int = 0
    failure_reason: str | None = None
    next_attempt_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    finished_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.kind.strip() or not self.idempotency_key.strip():
            raise DomainValidationError("job kind and idempotency key are required")
        if not self.trace_id.strip():
            raise DomainValidationError("job trace id is required")
        if self.max_attempts < 1 or self.timeout_seconds < 1:
            raise DomainValidationError("job retry and timeout limits must be positive")
        if not 0 <= self.progress <= 100:
            raise DomainValidationError("job progress must be between 0 and 100")

    def start(self, now: datetime | None = None) -> "Job":
        if self.status not in {JobStatus.QUEUED, JobStatus.RETRYING}:
            raise InvalidStateTransitionError(f"cannot start job from {self.status}")
        timestamp = now or datetime.now(UTC)
        return replace(
            self,
            status=JobStatus.RUNNING,
            stage="running",
            attempt=self.attempt + 1,
            started_at=timestamp,
            next_attempt_at=None,
        )

    def report_progress(self, progress: int, stage: str) -> "Job":
        if self.status is not JobStatus.RUNNING:
            raise InvalidStateTransitionError("only a running job can report progress")
        if progress < self.progress or not 0 <= progress <= 99:
            raise DomainValidationError("running job progress must increase and stay below 100")
        if not stage.strip():
            raise DomainValidationError("job stage is required")
        return replace(self, progress=progress, stage=stage)

    def succeed(self, now: datetime | None = None) -> "Job":
        if self.status is not JobStatus.RUNNING:
            raise InvalidStateTransitionError("only a running job can succeed")
        return replace(
            self,
            status=JobStatus.SUCCEEDED,
            progress=100,
            stage="succeeded",
            finished_at=now or datetime.now(UTC),
        )

    def fail(
        self,
        reason: str,
        *,
        retryable: bool,
        retry_delay: timedelta = timedelta(seconds=30),
        now: datetime | None = None,
    ) -> "Job":
        if self.status is not JobStatus.RUNNING:
            raise InvalidStateTransitionError("only a running job can fail")
        if not reason.strip():
            raise DomainValidationError("failure reason is required")
        timestamp = now or datetime.now(UTC)
        can_retry = retryable and self.attempt < self.max_attempts
        return replace(
            self,
            status=JobStatus.RETRYING if can_retry else JobStatus.FAILED,
            stage="waiting_to_retry" if can_retry else "failed",
            failure_reason=reason,
            next_attempt_at=timestamp + retry_delay if can_retry else None,
            finished_at=None if can_retry else timestamp,
        )

    def cancel(self, now: datetime | None = None) -> "Job":
        if self.status in TERMINAL_JOB_STATUSES:
            raise InvalidStateTransitionError(f"cannot cancel job from {self.status}")
        return replace(
            self,
            status=JobStatus.CANCELLED,
            stage="cancelled",
            finished_at=now or datetime.now(UTC),
        )
