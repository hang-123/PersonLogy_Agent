"""Conversation source objects used by the import boundary."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

from personlogy.shared.errors import DomainValidationError


@dataclass(frozen=True, slots=True)
class Conversation:
    project_id: UUID
    source_id: UUID
    external_id: str
    title: str
    metadata: dict[str, object] = field(default_factory=dict)
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not self.external_id.strip() or not self.title.strip():
            raise DomainValidationError("conversation id and title are required")


@dataclass(frozen=True, slots=True)
class ConversationMessage:
    conversation_id: UUID
    external_id: str
    role: str
    content: str
    ordinal: int
    content_hash: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    parent_external_id: str | None = None
    attachments: tuple[dict[str, object], ...] = ()
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        if not self.external_id.strip() or not self.role.strip() or not self.content.strip():
            raise DomainValidationError("message id, role, and content are required")
        if self.ordinal < 0:
            raise DomainValidationError("message ordinal cannot be negative")
        if not self.content_hash.strip():
            raise DomainValidationError("message content hash is required")
