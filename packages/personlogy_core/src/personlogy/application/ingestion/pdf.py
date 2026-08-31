"""Application services for PDF upload and asynchronous parsing."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from uuid import UUID

from personlogy.application.lineage import add_lineage_link
from personlogy.application.orchestration import JobService
from personlogy.domain.job import Job
from personlogy.domain.source.models import (
    ContentBlock,
    Project,
    Source,
    SourceKind,
    SourceVersion,
)
from personlogy.ports.ingestion import ObjectStorage, PdfParser
from personlogy.ports.lineage import LineageStore
from personlogy.ports.unit_of_work import UnitOfWorkFactory
from personlogy.shared.errors import DomainValidationError


class PdfUploadError(DomainValidationError):
    """Raised when an uploaded file is not an acceptable PDF."""


@dataclass(frozen=True, slots=True)
class PdfImportResult:
    project_id: UUID
    source_id: UUID
    source_version_id: UUID
    version: int
    content_hash: str
    object_key: str
    page_count: int
    job: Job
    reused_version: bool


class PdfImportService:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        job_service: JobService,
        storage: ObjectStorage,
        parser: PdfParser,
        *,
        max_size_bytes: int,
        lineage_store: LineageStore | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._job_service = job_service
        self._storage = storage
        self._parser = parser
        self._max_size_bytes = max_size_bytes
        self._lineage_store = lineage_store

    async def import_pdf(
        self,
        *,
        project_name: str,
        project_slug: str,
        title: str,
        filename: str,
        content_type: str | None,
        content: bytes,
    ) -> PdfImportResult:
        self._validate_upload(filename, content_type, content)
        try:
            page_count = self._parser.validate(content)
        except ValueError as error:
            raise PdfUploadError(str(error)) from error

        content_hash = _content_hash(content)
        async with self._uow_factory() as uow:
            project = await uow.sources.get_project_by_slug(project_slug)
            if project is None:
                project = Project(name=project_name, slug=project_slug)
                await uow.sources.add_project(project)

            existing = await uow.sources.get_pdf_version_by_hash(project.id, content_hash)
            if existing is not None:
                source_id = existing.source_id
                version = existing
                reused_version = True
                # Re-uploading the same hash also repairs a missing local object.
                await self._storage.put(version.object_key, content)
            else:
                source = await uow.sources.get_source(project.id, SourceKind.PDF, title)
                if source is None:
                    source = Source(project.id, SourceKind.PDF, title)
                    await uow.sources.add_source(source)
                version = SourceVersion(
                    source_id=source.id,
                    version=await uow.sources.next_version_number(source.id),
                    content_hash=content_hash,
                    object_key=f"projects/{project.id}/pdf/{content_hash}.pdf",
                )
                await self._storage.put(version.object_key, content)
                await uow.sources.add_version(version)
                source_id = source.id
                reused_version = False
            await uow.commit()

        job = await self._job_service.submit(
            kind="pdf.parse",
            idempotency_key=f"pdf-parse:{version.id}",
            payload={
                "project_id": str(project.id),
                "source_id": str(source_id),
                "source_version_id": str(version.id),
                "object_key": version.object_key,
                "content_hash": version.content_hash,
            },
        )
        await add_lineage_link(
            self._lineage_store,
            project_id=project.id,
            from_type="source",
            from_id=source_id,
            relation_type="has_version",
            to_type="source_version",
            to_id=version.id,
        )
        await add_lineage_link(
            self._lineage_store,
            project_id=project.id,
            from_type="job",
            from_id=job.id,
            relation_type="input",
            to_type="source_version",
            to_id=version.id,
        )
        return PdfImportResult(
            project_id=project.id,
            source_id=source_id,
            source_version_id=version.id,
            version=version.version,
            content_hash=version.content_hash,
            object_key=version.object_key,
            page_count=page_count,
            job=job,
            reused_version=reused_version,
        )

    async def process_pdf_job(self, job: Job) -> int:
        if job.kind != "pdf.parse":
            raise DomainValidationError(f"unsupported PDF job kind: {job.kind}")
        version_id = _payload_uuid(job, "source_version_id")
        object_key = _payload_string(job, "object_key")
        content = await self._storage.read(object_key)
        parsed_blocks = self._parser.parse(content)
        if not parsed_blocks:
            raise PdfUploadError("PDF contains no extractable text or tables")

        async with self._uow_factory() as uow:
            version = await uow.sources.get_version(version_id)
            if version is None:
                raise DomainValidationError("source version does not exist")
            existing_blocks = await uow.sources.list_blocks(version.id)
            if existing_blocks:
                return len(existing_blocks)
            for ordinal, parsed in enumerate(parsed_blocks):
                block = ContentBlock(
                    source_version_id=version.id,
                    ordinal=ordinal,
                    content=parsed.content,
                    content_hash=_content_hash(parsed.content.encode("utf-8")),
                    locator=parsed.locator,
                )
                await uow.sources.add_block(block)
            await uow.commit()
        return len(parsed_blocks)

    def _validate_upload(
        self, filename: str, content_type: str | None, content: bytes
    ) -> None:
        if len(content) > self._max_size_bytes:
            raise PdfUploadError(f"PDF exceeds maximum size of {self._max_size_bytes} bytes")
        if not filename.lower().endswith(".pdf"):
            raise PdfUploadError("file extension must be .pdf")
        if content_type and content_type.lower() != "application/pdf":
            raise PdfUploadError("content type must be application/pdf")
        if not content.startswith(b"%PDF-"):
            raise PdfUploadError("file header is not a PDF")


def _content_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _payload_string(job: Job, key: str) -> str:
    value = job.payload.get(key)
    if not isinstance(value, str) or not value:
        raise DomainValidationError(f"PDF job payload field is missing: {key}")
    return value


def _payload_uuid(job: Job, key: str) -> UUID:
    try:
        return UUID(_payload_string(job, key))
    except ValueError as error:
        raise DomainValidationError(f"PDF job payload field is invalid: {key}") from error
