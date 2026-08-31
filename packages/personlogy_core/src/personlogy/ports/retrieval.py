"""Provider-independent retrieval ports and result value objects."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class Evidence:
    citation_id: UUID
    quote: str
    source_id: UUID
    source_title: str
    source_version_id: UUID
    locator: dict[str, object]


@dataclass(frozen=True, slots=True)
class RelationPath:
    relation_id: UUID
    relation_type: str
    direction: str
    source_id: UUID
    source_title: str
    target_id: UUID
    target_title: str


@dataclass(frozen=True, slots=True)
class RetrievalHit:
    claim_id: UUID
    project_id: UUID
    statement: str
    subject_id: UUID
    subject_title: str
    score: float
    evidence: tuple[Evidence, ...]
    relations: tuple[RelationPath, ...]


@dataclass(frozen=True, slots=True)
class EmbeddingVector:
    model_name: str
    model_version: str
    values: tuple[float, ...]

    @property
    def dimensions(self) -> int:
        return len(self.values)


@dataclass(frozen=True, slots=True)
class SemanticHit:
    document_id: UUID
    score: float
    model_name: str
    model_version: str


class EmbeddingProvider(Protocol):
    model_name: str
    model_version: str

    async def embed(self, texts: Sequence[str]) -> tuple[EmbeddingVector, ...]: ...


class SemanticRetriever(Protocol):
    async def search(
        self,
        *,
        project_id: UUID,
        query_vector: EmbeddingVector,
        limit: int = 20,
    ) -> tuple[SemanticHit, ...]: ...


class RetrievalReader(Protocol):
    async def search(
        self,
        *,
        project_id: UUID,
        query: str,
        limit: int = 20,
        expand_relations: bool = False,
    ) -> tuple[RetrievalHit, ...]: ...


class RetrievalIndexer(Protocol):
    async def rebuild_project(self, project_id: UUID, *, job_id: UUID | None = None) -> int: ...


__all__ = [
    "EmbeddingProvider",
    "EmbeddingVector",
    "Evidence",
    "RelationPath",
    "RetrievalHit",
    "RetrievalIndexer",
    "RetrievalReader",
    "SemanticHit",
    "SemanticRetriever",
]
