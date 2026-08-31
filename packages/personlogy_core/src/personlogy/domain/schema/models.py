"""Versioned schema-management domain models."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import cast
from uuid import UUID, uuid4

from personlogy.shared.errors import DomainValidationError


class SchemaProposalStatus(StrEnum):
    DRAFT = "draft"
    VALIDATED = "validated"
    APPROVED = "approved"
    APPLIED = "applied"
    ROLLED_BACK = "rolled_back"
    REJECTED = "rejected"


class SchemaChangeKind(StrEnum):
    ADD_ENTITY = "add_entity"
    REMOVE_ENTITY = "remove_entity"
    ADD_FIELD = "add_field"
    REMOVE_FIELD = "remove_field"
    CHANGE_FIELD = "change_field"


@dataclass(frozen=True, slots=True)
class SchemaSnapshot:
    namespace: str
    version: int
    definition: dict[str, object]
    checksum: str
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def create(
        cls, *, namespace: str, version: int, definition: dict[str, object]
    ) -> SchemaSnapshot:
        canonical = _canonical_definition(definition)
        return cls(
            namespace=namespace,
            version=version,
            definition=definition,
            checksum=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        )

    def __post_init__(self) -> None:
        if not self.namespace.strip():
            raise DomainValidationError("schema namespace is required")
        if self.version < 1:
            raise DomainValidationError("schema version must be positive")
        if not self.checksum.strip():
            raise DomainValidationError("schema checksum is required")
        if not isinstance(self.definition, dict):
            raise DomainValidationError("schema definition must be an object")


@dataclass(frozen=True, slots=True)
class SchemaChange:
    kind: SchemaChangeKind
    path: str
    before: object | None = None
    after: object | None = None


@dataclass(frozen=True, slots=True)
class SchemaProposal:
    namespace: str
    base_version: int
    target_version: int
    definition: dict[str, object]
    changes: tuple[SchemaChange, ...]
    author: str
    status: SchemaProposalStatus = SchemaProposalStatus.DRAFT
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    validated_at: datetime | None = None
    approved_by: str | None = None
    approved_at: datetime | None = None
    applied_at: datetime | None = None
    rolled_back_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.namespace.strip():
            raise DomainValidationError("schema proposal namespace is required")
        if self.base_version < 1 or self.target_version <= self.base_version:
            raise DomainValidationError("schema proposal versions are invalid")
        if not self.author.strip():
            raise DomainValidationError("schema proposal author is required")
        if not isinstance(self.definition, dict):
            raise DomainValidationError("schema proposal definition must be an object")


def _canonical_definition(definition: dict[str, object]) -> str:
    return json.dumps(definition, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def as_definition(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise DomainValidationError("stored schema definition must be an object")
    return cast(dict[str, object], value)


__all__ = [
    "SchemaChange",
    "SchemaChangeKind",
    "SchemaProposal",
    "SchemaProposalStatus",
    "SchemaSnapshot",
    "as_definition",
]
