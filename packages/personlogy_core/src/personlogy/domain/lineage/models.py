"""Domain model for an append-only derived-entity relationship."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

from personlogy.domain.audit import sanitize_metadata
from personlogy.shared.errors import DomainValidationError


@dataclass(frozen=True, slots=True)
class LineageLink:
    project_id: UUID
    from_type: str
    from_id: str
    relation_type: str
    to_type: str
    to_id: str
    link_id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for field_name in ("from_type", "from_id", "relation_type", "to_type", "to_id"):
            if not getattr(self, field_name).strip():
                raise DomainValidationError(f"lineage {field_name} is required")
        if self.from_type == self.to_type and self.from_id == self.to_id:
            raise DomainValidationError("lineage link cannot point to itself")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise DomainValidationError("lineage created_at must be timezone-aware")
        if not isinstance(self.metadata, Mapping):
            raise DomainValidationError("lineage metadata must be a mapping")
        object.__setattr__(self, "metadata", sanitize_metadata(self.metadata))


__all__ = ["LineageLink"]
