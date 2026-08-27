from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

from personlogy.domain.knowledge.models import VerificationStatus
from personlogy.shared.errors import DomainValidationError

INITIAL_RELATION_TYPES = (
    "is_a",
    "part_of",
    "depends_on",
    "supports",
    "contradicts",
    "related_to",
    "derived_from",
)


@dataclass(frozen=True, slots=True)
class RelationType:
    key: str
    label: str
    description: str = ""
    directional: bool = True

    def __post_init__(self) -> None:
        if not self.key.strip() or not self.label.strip():
            raise DomainValidationError("relation type key and label are required")


@dataclass(frozen=True, slots=True)
class Relation:
    project_id: UUID
    relation_type: str
    source_id: UUID
    target_id: UUID
    citation_ids: tuple[UUID, ...]
    properties: dict[str, object] = field(default_factory=dict)
    confidence: float | None = None
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    status: VerificationStatus = VerificationStatus.CANDIDATE
    metadata: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.relation_type.strip():
            raise DomainValidationError("relation type is required")
        if self.source_id == self.target_id and self.relation_type != "related_to":
            raise DomainValidationError("directed relation endpoints must be different")
        if not self.citation_ids:
            raise DomainValidationError("relation must have at least one citation")
        if self.confidence is not None and not 0 <= self.confidence <= 1:
            raise DomainValidationError("relation confidence must be between 0 and 1")
