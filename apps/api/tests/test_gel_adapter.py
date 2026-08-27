"""Gel adapter integration tests.

These tests require a running Gel server and a database with the project
schema applied (see ``GEL/README.md``). They are skipped unless
``PKS_GEL_TEST_DSN`` is set, so development machines without a Gel instance
(including CI) can run the rest of the suite untouched.

Example:

    set PKS_GEL_TEST_DSN=gel://edgedb@localhost:5656/personlogy?tls_security=insecure
    pytest tests/test_gel_adapter.py
"""

import asyncio
import os
from pathlib import Path
from uuid import uuid4

import pytest
from personlogy.adapters.gel import GelJobQueue, GelStore, GelUnitOfWorkFactory
from personlogy.adapters.local_files import LocalFileStorage
from personlogy.adapters.pdf import PdfPlumberParser
from personlogy.application.ingestion import PdfImportService
from personlogy.application.orchestration import JobService
from personlogy.domain.job import JobStatus
from personlogy.domain.knowledge.models import Citation, Claim, KnowledgeNode
from personlogy.domain.relation.models import Relation
from personlogy.domain.source.models import ContentBlock, Project, Source, SourceKind, SourceVersion

GEL_DSN = os.getenv("PKS_GEL_TEST_DSN")

pytestmark = pytest.mark.skipif(
    not GEL_DSN, reason="set PKS_GEL_TEST_DSN to run Gel integration tests"
)


def _store() -> GelStore:
    assert GEL_DSN is not None
    return GelStore(GEL_DSN)


def test_pdf_import_persists_blocks_on_gel(tmp_path: Path) -> None:
    asyncio.run(_test_pdf_import_persists_blocks_on_gel(tmp_path))


async def _test_pdf_import_persists_blocks_on_gel(tmp_path: Path) -> None:
    store = _store()
    try:
        factory = GelUnitOfWorkFactory(store)
        service = PdfImportService(
            factory,
            JobService(factory, GelJobQueue(store, poll_interval_seconds=0.01)),
            LocalFileStorage(tmp_path / "files"),
            PdfPlumberParser(),
            max_size_bytes=1024 * 1024,
        )
        slug = f"gel-pdf-{uuid4()}"
        content = _sample_pdf()

        first = await service.import_pdf(
            project_name="Gel PDF 测试",
            project_slug=slug,
            title="示例文档",
            filename="sample.pdf",
            content_type="application/pdf",
            content=content,
        )
        block_count = await service.process_pdf_job(first.job)
        second = await service.import_pdf(
            project_name="Gel PDF 测试",
            project_slug=slug,
            title="示例文档",
            filename="sample.pdf",
            content_type="application/pdf",
            content=content,
        )

        assert first.page_count == 1
        assert block_count == 1
        assert first.reused_version is False
        assert second.reused_version is True
        assert second.source_version_id == first.source_version_id

        async with factory() as uow:
            project = await uow.sources.get_project_by_slug(slug)
            assert project is not None
            blocks = await uow.sources.list_blocks(first.source_version_id)
            assert blocks[0].content == "Hello PDF"
            assert blocks[0].locator == {"page": 1, "paragraph": 0, "block_type": "heading"}
            job = await uow.jobs.get(first.job.id)
            assert job is not None
            assert job.status is JobStatus.QUEUED
            assert job.kind == "pdf.parse"
    finally:
        await store.aclose()


def test_knowledge_repository_roundtrip_on_gel() -> None:
    asyncio.run(_test_knowledge_repository_roundtrip_on_gel())


async def _test_knowledge_repository_roundtrip_on_gel() -> None:
    store = _store()
    try:
        factory = GelUnitOfWorkFactory(store)
        suffix = uuid4()
        async with factory() as uow:
            project = Project(name=f"gel-knowledge-{suffix}", slug=f"gel-knowledge-{suffix}")
            await uow.sources.add_project(project)
            source = Source(project.id, SourceKind.PDF, "知识测试")
            await uow.sources.add_source(source)
            version = SourceVersion(
                source_id=source.id, version=1, content_hash="h1", object_key="k1"
            )
            await uow.sources.add_version(version)
            block = ContentBlock(
                source_version_id=version.id,
                ordinal=0,
                content="quote text",
                content_hash="h2",
                locator={"page": 1},
            )
            await uow.sources.add_block(block)
            node = KnowledgeNode(project.id, "concept", "测试概念")
            await uow.knowledge.add_node(node)
            citation = Citation(block.id, "quote text", {"page": 1})
            await uow.knowledge.add_citation(citation)
            claim = Claim(
                project_id=project.id,
                subject_id=node.id,
                statement="测试声明",
                citations=(citation,),
                confidence=0.9,
            )
            await uow.knowledge.add_claim(claim)
            # RelationType is seeded by GEL/seed.edgeql, reuse it here.
            # Note: a failed statement aborts the whole Gel transaction,
            # so errors must not be swallowed inside a UoW.
            relation = Relation(
                project_id=project.id,
                relation_type="related_to",
                source_id=node.id,
                target_id=node.id,
                citation_ids=(citation.id,),
            )
            await uow.knowledge.add_relation(relation)
            await uow.commit()

        async with factory() as uow:
            stored_project = await uow.sources.get_project_by_slug(project.slug)
            assert stored_project is not None
            stored_source = await uow.sources.get_source(
                stored_project.id, SourceKind.PDF, "知识测试"
            )
            assert stored_source is not None
            stored_version = await uow.sources.get_version(version.id)
            assert stored_version is not None
            assert stored_version.content_hash == "h1"
            blocks = await uow.sources.list_blocks(version.id)
            assert len(blocks) == 1
            job_list = await uow.jobs.list(limit=5)
            assert isinstance(job_list, list)
    finally:
        await store.aclose()


def test_gel_rolls_back_uncommitted_uow() -> None:
    asyncio.run(_test_gel_rolls_back_uncommitted_uow())


async def _test_gel_rolls_back_uncommitted_uow() -> None:
    store = _store()
    try:
        factory = GelUnitOfWorkFactory(store)
        slug = f"gel-rollback-{uuid4()}"
        async with factory() as uow:
            await uow.sources.add_project(Project(name=slug, slug=slug))
            # no commit() call: exiting the UoW must roll back
        async with factory() as uow:
            assert await uow.sources.get_project_by_slug(slug) is None
    finally:
        await store.aclose()


def _sample_pdf() -> bytes:
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 300] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length 41 >>\nstream\nBT /F1 12 Tf 50 250 Td (Hello PDF) Tj ET\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    data = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, body in enumerate(objects, start=1):
        offsets.append(len(data))
        data.extend(f"{index} 0 obj\n".encode())
        data.extend(body)
        data.extend(b"\nendobj\n")
    xref = len(data)
    data.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    data.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        data.extend(f"{offset:010d} 00000 n \n".encode())
    data.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref}\n%%EOF\n".encode()
    )
    return bytes(data)
