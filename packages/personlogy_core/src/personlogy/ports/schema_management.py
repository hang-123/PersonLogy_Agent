"""Ports for the decoupled schema-management infrastructure."""

from typing import Protocol
from uuid import UUID

from personlogy.domain.schema.models import SchemaProposal, SchemaSnapshot


class SchemaRegistry(Protocol):
    async def get_current_snapshot(self, namespace: str) -> SchemaSnapshot | None: ...

    async def get_snapshot(self, namespace: str, version: int) -> SchemaSnapshot | None: ...

    async def save_snapshot(self, snapshot: SchemaSnapshot) -> None: ...

    async def save_snapshot_if_current(
        self, snapshot: SchemaSnapshot, *, expected_version: int
    ) -> None: ...

    async def save_proposal(self, proposal: SchemaProposal) -> None: ...

    async def get_proposal(self, proposal_id: UUID) -> SchemaProposal | None: ...


class MigrationExecutor(Protocol):
    async def apply(
        self, *, proposal: SchemaProposal, current: SchemaSnapshot
    ) -> None: ...

    async def rollback(
        self,
        *,
        proposal: SchemaProposal,
        current: SchemaSnapshot,
        target: SchemaSnapshot,
    ) -> None: ...


__all__ = ["MigrationExecutor", "SchemaRegistry"]
