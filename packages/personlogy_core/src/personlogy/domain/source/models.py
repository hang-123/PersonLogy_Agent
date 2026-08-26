from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from personlogy.shared.errors import DomainValidationError


class SourceKind(StrEnum):
    PDF = "pdf"
    CONVERSATION = "conversation"


@dataclass(frozen=True, slots=True)
class Project:
    name: str
    slug: str
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.slug.strip():
            raise DomainValidationError("project name and slug are required")


@dataclass(frozen=True, slots=True)
class Source:
    project_id: UUID
    kind: SourceKind
    title: str
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise DomainValidationError("source title is required")


@dataclass(frozen=True, slots=True)
class SourceVersion:
    source_id: UUID
    version: int
    content_hash: str
    object_key: str
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if self.version < 1:
            raise DomainValidationError("source version must be positive")
        if not self.content_hash.strip() or not self.object_key.strip():
            raise DomainValidationError("content hash and object key are required")


@dataclass(frozen=True, slots=True)
class ContentBlock:
    source_version_id: UUID
    ordinal: int
    content: str
    content_hash: str
    locator: dict[str, object]
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        if self.ordinal < 0:
            raise DomainValidationError("content block ordinal cannot be negative")
        if not self.content.strip() or not self.content_hash.strip():
            raise DomainValidationError("content and content hash are required")
