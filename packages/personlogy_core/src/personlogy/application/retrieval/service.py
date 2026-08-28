"""Hybrid retrieval application service."""

from uuid import UUID

from personlogy.ports.retrieval import RetrievalHit, RetrievalReader
from personlogy.shared.errors import DomainValidationError


class RetrievalService:
    def __init__(self, reader: RetrievalReader) -> None:
        self._reader = reader

    async def search(
        self,
        *,
        project_id: UUID,
        query: str,
        limit: int = 20,
        expand_relations: bool = False,
    ) -> tuple[RetrievalHit, ...]:
        if not query.strip():
            raise DomainValidationError("retrieval query is required")
        if not 1 <= limit <= 100:
            raise DomainValidationError("retrieval limit must be between 1 and 100")
        return await self._reader.search(
            project_id=project_id,
            query=query.strip(),
            limit=limit,
            expand_relations=expand_relations,
        )


__all__ = ["RetrievalService"]
