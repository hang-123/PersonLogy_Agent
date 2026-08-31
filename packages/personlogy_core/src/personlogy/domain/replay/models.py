"""Immutable replay plans and non-publishing comparison candidates."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from personlogy.shared.errors import DomainValidationError


class ReplayPlanStatus(StrEnum):
    PROPOSED = "proposed"
    QUEUED = "queued"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ReplayDifferenceDimension(StrEnum):
    INPUT = "input"
    SCHEMA = "schema"
    COMPILER = "compiler"
    EMBEDDING = "embedding"
    INDEX = "index"
    OUTPUT = "output"


@dataclass(frozen=True, slots=True)
class ReplayVersionSet:
    schema_version: str | None = None
    compiler_version: str = "unknown"
    embedding_version: str | None = None
    index_version: int | None = None

    def __post_init__(self) -> None:
        if not self.compiler_version.strip():
            raise DomainValidationError("replay compiler version is required")
        if self.schema_version is not None and not self.schema_version.strip():
            raise DomainValidationError("replay schema version cannot be blank")
        if self.embedding_version is not None and not self.embedding_version.strip():
            raise DomainValidationError("replay embedding version cannot be blank")
        if self.index_version is not None and self.index_version < 1:
            raise DomainValidationError("replay index version must be positive")


@dataclass(frozen=True, slots=True)
class ReplayPlan:
    project_id: UUID
    source_version_id: UUID
    parent_trace_id: str
    baseline_input_content_hash: str
    baseline_versions: ReplayVersionSet
    target_input_content_hash: str
    target_versions: ReplayVersionSet
    parent_job_id: UUID | None = None
    plan_id: UUID = field(default_factory=uuid4)
    status: ReplayPlanStatus = ReplayPlanStatus.PROPOSED
    replay_job_id: UUID | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    approved_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.parent_trace_id.strip():
            raise DomainValidationError("replay parent trace id is required")
        if (
            not self.baseline_input_content_hash.strip()
            or not self.target_input_content_hash.strip()
        ):
            raise DomainValidationError("replay input content hashes are required")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise DomainValidationError("replay plan timestamp must be timezone-aware")
        if self.approved_at is not None and (
            self.approved_at.tzinfo is None or self.approved_at.utcoffset() is None
        ):
            raise DomainValidationError("replay approval timestamp must be timezone-aware")
        if self.status is ReplayPlanStatus.PROPOSED and self.replay_job_id is not None:
            raise DomainValidationError("proposed replay plan cannot have a replay job")
        if self.status is ReplayPlanStatus.QUEUED and self.replay_job_id is None:
            raise DomainValidationError("queued replay plan requires a replay job")


@dataclass(frozen=True, slots=True)
class ReplayComparison:
    project_id: UUID
    plan_id: UUID
    source_version_id: UUID
    replay_job_id: UUID
    difference_dimensions: tuple[str, ...]
    output_changed: bool | None
    original_output_digest: str | None = None
    replay_output_digest: str | None = None
    status: str = "candidate"
    comparison_id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        allowed = {item.value for item in ReplayDifferenceDimension}
        if any(item not in allowed for item in self.difference_dimensions):
            raise DomainValidationError("replay comparison dimension is invalid")
        if self.status != "candidate":
            raise DomainValidationError("replay comparison must remain a candidate in P10-E")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise DomainValidationError("replay comparison timestamp must be timezone-aware")
        for name, value in (
            ("original_output_digest", self.original_output_digest),
            ("replay_output_digest", self.replay_output_digest),
        ):
            if value is not None and (
                len(value) != 64 or any(character not in "0123456789abcdef" for character in value)
            ):
                raise DomainValidationError(f"{name} must be a SHA-256 hexadecimal digest")
        if self.output_changed is True and (
            self.original_output_digest is None or self.replay_output_digest is None
        ):
            raise DomainValidationError("changed replay output requires both output digests")


__all__ = [
    "ReplayComparison",
    "ReplayDifferenceDimension",
    "ReplayPlan",
    "ReplayPlanStatus",
    "ReplayVersionSet",
]
