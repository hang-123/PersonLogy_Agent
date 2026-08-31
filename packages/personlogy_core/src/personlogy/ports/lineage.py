"""Persistence contracts for read-only lineage queries."""

from typing import Protocol
from uuid import UUID

from personlogy.domain.lineage import LineageLink


class LineageStore(Protocol):
    async def add_link(self, link: LineageLink) -> LineageLink: ...

    async def trace_entity(
        self,
        *,
        project_id: UUID,
        entity_type: str,
        entity_id: str,
        limit: int = 1000,
    ) -> list[LineageLink]: ...


__all__ = ["LineageStore"]
