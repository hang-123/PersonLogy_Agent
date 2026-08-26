from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from personlogy.shared.errors import DomainValidationError


class VerificationStatus(StrEnum):
    CANDIDATE = "candidate"
    MACHINE_CHECKED = "machine_checked"
    HUMAN_VERIFIED = "human_verified"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class KnowledgeNode:
    project_id: UUID
    node_type: str
    title: str
    properties: dict[str, object] = field(default_factory=dict)
    status: VerificationStatus = VerificationStatus.CANDIDATE
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not self.node_type.strip() or not self.title.strip():
            raise DomainValidationError("knowledge node type and title are required")


@dataclass(frozen=True, slots=True)
class Citation:
    content_block_id: UUID
    quote: str
    locator: dict[str, object]
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        if not self.quote.strip():
            raise DomainValidationError("citation quote is required")


@dataclass(frozen=True, slots=True)
class Claim:
    project_id: UUID
    subject_id: UUID
    statement: str
    citations: tuple[Citation, ...]
    confidence: float | None = None
    status: VerificationStatus = VerificationStatus.CANDIDATE
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not self.statement.strip():
            raise DomainValidationError("claim statement is required")
        if not self.citations:
            raise DomainValidationError("claim must have at least one citation")
        if self.confidence is not None and not 0 <= self.confidence <= 1:
            raise DomainValidationError("claim confidence must be between 0 and 1")
