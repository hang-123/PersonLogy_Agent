from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from personlogy.shared.errors import DomainValidationError


class ReviewDecision(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"
    REVISED = "revised"


@dataclass(frozen=True, slots=True)
class ReviewRecord:
    target_id: UUID
    reviewer_id: str
    decision: ReviewDecision
    note: str = ""
    before: dict[str, object] = field(default_factory=dict)
    after: dict[str, object] = field(default_factory=dict)
    id: UUID = field(default_factory=uuid4)
    reviewed_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not self.reviewer_id.strip():
            raise DomainValidationError("reviewer id is required")
