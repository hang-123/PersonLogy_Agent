"""Ports for the decoupled schema-management infrastructure."""

from typing import Protocol
from uuid import UUID

from personlogy.domain.schema.models import SchemaProposal, SchemaSnapshot


class SchemaRegistry(Protocol):
    async def get_current_snapshot(self, namespace: str) -> SchemaSnapshot | None: ...

    async def save_snapshot(self, snapshot: SchemaSnapshot) -> None: ...

    async def save_proposal(self, proposal: SchemaProposal) -> None: ...

    async def get_proposal(self, proposal_id: UUID) -> SchemaProposal | None: ...


__all__ = ["SchemaRegistry"]
