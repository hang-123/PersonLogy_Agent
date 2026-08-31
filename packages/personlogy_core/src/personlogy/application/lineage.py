"""Lineage recording helpers and project-scoped read-only traces."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from uuid import UUID

from personlogy.domain.lineage import LineageLink
from personlogy.ports.lineage import LineageStore


@dataclass(frozen=True, slots=True)
class LineageTrace:
    root_type: str
    root_id: str
    links: tuple[LineageLink, ...]


async def add_lineage_link(
    lineage_store: LineageStore | None,
    *,
    project_id: UUID,
    from_type: str,
    from_id: UUID | str,
    relation_type: str,
    to_type: str,
    to_id: UUID | str,
    metadata: Mapping[str, object] | None = None,
) -> LineageLink | None:
    if lineage_store is None:
        return None
    return await lineage_store.add_link(
        LineageLink(
            project_id=project_id,
            from_type=from_type,
            from_id=str(from_id),
            relation_type=relation_type,
            to_type=to_type,
            to_id=str(to_id),
            metadata=metadata or {},
        )
    )


class LineageService:
    def __init__(self, lineage_store: LineageStore) -> None:
        self._lineage_store = lineage_store

    async def trace_entity(
        self,
        *,
        project_id: UUID,
        entity_type: str,
        entity_id: UUID | str,
        limit: int = 1000,
    ) -> LineageTrace:
        links = await self._lineage_store.trace_entity(
            project_id=project_id,
            entity_type=entity_type,
            entity_id=str(entity_id),
            limit=limit,
        )
        return LineageTrace(entity_type, str(entity_id), tuple(links))

    async def trace_claim(
        self, *, project_id: UUID, claim_id: UUID, limit: int = 1000
    ) -> LineageTrace:
        return await self.trace_entity(
            project_id=project_id,
            entity_type="claim",
            entity_id=claim_id,
            limit=limit,
        )

    async def trace_source_version(
        self, *, project_id: UUID, source_version_id: UUID, limit: int = 1000
    ) -> LineageTrace:
        return await self.trace_entity(
            project_id=project_id,
            entity_type="source_version",
            entity_id=source_version_id,
            limit=limit,
        )

    async def trace_job(self, *, project_id: UUID, job_id: UUID, limit: int = 1000) -> LineageTrace:
        return await self.trace_entity(
            project_id=project_id,
            entity_type="job",
            entity_id=job_id,
            limit=limit,
        )

    async def trace_retrieval(
        self, *, project_id: UUID, request_id: str, limit: int = 1000
    ) -> LineageTrace:
        return await self.trace_entity(
            project_id=project_id,
            entity_type="retrieval_request",
            entity_id=request_id,
            limit=limit,
        )


__all__ = ["LineageService", "LineageTrace", "add_lineage_link"]
