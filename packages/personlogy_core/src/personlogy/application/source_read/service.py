"""Application services for reading source versions and evidence."""

from dataclasses import dataclass
from uuid import UUID

from personlogy.domain.knowledge.models import Citation
from personlogy.domain.source.models import ContentBlock, SourceVersion
from personlogy.ports.ingestion import ObjectStorage
from personlogy.ports.unit_of_work import UnitOfWorkFactory


@dataclass(frozen=True, slots=True)
class SourceVersionDetail:
    version: SourceVersion
    blocks: tuple[ContentBlock, ...]


@dataclass(frozen=True, slots=True)
class EvidenceDetail:
    citation: Citation
    block: ContentBlock
    version: SourceVersion


class SourceReadService:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        storage: ObjectStorage | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._storage = storage

    async def get_source_version(
        self, version_id: UUID, *, project_id: UUID | None = None
    ) -> SourceVersionDetail | None:
        async with self._uow_factory() as uow:
            version = (
                await uow.sources.get_version_in_project(project_id, version_id)
                if project_id is not None
                else await uow.sources.get_version(version_id)
            )
            if version is None:
                return None
            blocks = tuple(await uow.sources.list_blocks(version.id))
        return SourceVersionDetail(version=version, blocks=blocks)

    async def get_evidence(
        self, evidence_id: UUID, *, project_id: UUID | None = None
    ) -> EvidenceDetail | None:
        async with self._uow_factory() as uow:
            citation = await uow.knowledge.get_citation(evidence_id)
            if citation is None:
                return None
            block = await uow.sources.get_block(citation.content_block_id)
            if block is None:
                return None
            version = (
                await uow.sources.get_version_in_project(project_id, block.source_version_id)
                if project_id is not None
                else await uow.sources.get_version(block.source_version_id)
            )
            if version is None:
                return None
        return EvidenceDetail(citation=citation, block=block, version=version)

    async def read_source_content(
        self, version_id: UUID, *, project_id: UUID | None = None
    ) -> tuple[SourceVersion, bytes] | None:
        if self._storage is None:
            return None
        async with self._uow_factory() as uow:
            version = (
                await uow.sources.get_version_in_project(project_id, version_id)
                if project_id is not None
                else await uow.sources.get_version(version_id)
            )
        if version is None:
            return None
        return version, await self._storage.read(version.object_key)


__all__ = ["EvidenceDetail", "SourceReadService", "SourceVersionDetail"]
