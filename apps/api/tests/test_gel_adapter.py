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
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from personlogy.adapters.gel import GelJobQueue, GelStore, GelUnitOfWorkFactory
from personlogy.adapters.local_files import LocalFileStorage
from personlogy.adapters.pdf import PdfPlumberParser
from personlogy.application.governance import GovernanceService
from personlogy.application.ingestion import PdfImportService
from personlogy.application.orchestration import JobService
from personlogy.domain.governance.models import (
    CandidateKind,
    ConflictRecord,
    DuplicateGroup,
    GovernanceIssue,
    GovernanceIssueSeverity,
    GovernanceRun,
    GovernanceRunStatus,
    ReviewTask,
    ReviewTaskStatus,
)
from personlogy.domain.job import Job, JobStatus
from personlogy.domain.knowledge.models import Citation, Claim, KnowledgeNode, VerificationStatus
from personlogy.domain.relation.models import Relation
from personlogy.domain.source.models import ContentBlock, Project, Source, SourceKind, SourceVersion
from personlogy.shared.errors import DomainValidationError

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
            assert job.kind == "pdf.parse"
            # status is not asserted here: a live worker may have consumed it
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


def test_governance_repository_roundtrip_on_gel() -> None:
    asyncio.run(_test_governance_repository_roundtrip_on_gel())


async def _test_governance_repository_roundtrip_on_gel() -> None:
    store = _store()
    try:
        factory = GelUnitOfWorkFactory(store)
        suffix = uuid4()
        async with factory() as uow:
            project = Project(name=f"gel-gov-{suffix}", slug=f"gel-gov-{suffix}")
            await uow.sources.add_project(project)
            source = Source(project.id, SourceKind.PDF, "治理测试")
            await uow.sources.add_source(source)
            version = SourceVersion(source.id, 1, "gov-h1", "gov-k1")
            await uow.sources.add_version(version)
            block = ContentBlock(version.id, 0, "治理引用", "gov-bh1", {"page": 1})
            await uow.sources.add_block(block)
            node = KnowledgeNode(project.id, "concept", "治理概念")
            await uow.knowledge.add_node(node)
            citation = Citation(block.id, "治理引用", {"page": 1})
            await uow.knowledge.add_citation(citation)
            claim = Claim(project.id, node.id, "治理声明", (citation,), confidence=0.8)
            await uow.knowledge.add_claim(claim)
            relation = Relation(
                project.id, "related_to", node.id, node.id, (citation.id,)
            )
            await uow.knowledge.add_relation(relation)
            await uow.commit()

        run = GovernanceRun(
            project_id=project.id,
            task_id=uuid4(),
            rule_version="p6-rules-v1",
            status=GovernanceRunStatus.NEEDS_REVIEW,
            candidate_ids=(node.id, claim.id, relation.id),
        )
        issue = GovernanceIssue(
            run_id=run.id,
            candidate_id=claim.id,
            candidate_kind=CandidateKind.CLAIM,
            code="claim.missing_citation",
            message="claim has no citation",
            severity=GovernanceIssueSeverity.ERROR,
        )
        group = DuplicateGroup(project.id, (node.id, claim.id), "node.title")
        conflict = ConflictRecord(project.id, (claim.id, relation.id), "same_subject")
        tasks = (
            ReviewTask(run.id, node.id, CandidateKind.NODE),
            ReviewTask(run.id, claim.id, CandidateKind.CLAIM),
            ReviewTask(run.id, relation.id, CandidateKind.RELATION),
        )
        spare = ReviewTask(run.id, node.id, CandidateKind.NODE)

        async with factory() as uow:
            await uow.governance.add_run(run)
            await uow.governance.add_issue(issue)
            await uow.governance.add_duplicate_group(group)
            await uow.governance.add_conflict(conflict)
            for task in (*tasks, spare):
                await uow.governance.add_review_task(task)
            await uow.commit()

        async with factory() as uow:
            listed = await uow.governance.list_review_tasks(limit=10)
            stored = {task.id: task for task in listed}
            for task in (*tasks, spare):
                assert task.id in stored
                stored_task = stored[task.id]
                assert stored_task.run_id == run.id
                assert stored_task.candidate_kind is task.candidate_kind
                assert stored_task.status is ReviewTaskStatus.PENDING
                assert stored_task.version == 1
            fetched = await uow.governance.get_review_task(tasks[0].id)
            assert fetched is not None and fetched.candidate_id == node.id
            # version bump through direct save (spare is never decided below)
            bumped = replace(spare, status=ReviewTaskStatus.APPROVED, version=2)
            await uow.governance.save_review_task(bumped)
            await uow.commit()

        async with factory() as uow:
            after_save = await uow.governance.get_review_task(spare.id)
            assert after_save is not None and after_save.version == 2
            assert after_save.status is ReviewTaskStatus.APPROVED

        # Human decision flow writes candidate status back (NODE / CLAIM / RELATION paths)
        governance = GovernanceService(factory)
        claim_task = await governance.decide_review_task(
            tasks[1].id,
            decision=ReviewTaskStatus.APPROVED,
            reviewer_id="gel-reviewer",
            reason="source is clear",
            expected_version=1,
        )
        assert claim_task.status is ReviewTaskStatus.APPROVED
        assert claim_task.version == 2
        node_task = await governance.decide_review_task(
            tasks[0].id,
            decision=ReviewTaskStatus.REJECTED,
            reviewer_id="gel-reviewer",
            reason="duplicate of another node",
            expected_version=1,
        )
        assert node_task.status is ReviewTaskStatus.REJECTED
        relation_task = await governance.decide_review_task(
            tasks[2].id,
            decision=ReviewTaskStatus.REVISED,
            reviewer_id="gel-reviewer",
            reason="endpoint direction is wrong",
            expected_version=1,
        )
        assert relation_task.status is ReviewTaskStatus.REVISED

        async with factory() as uow:
            stored_claim = await uow.knowledge.get_claim(claim.id)
            assert stored_claim is not None
            assert stored_claim.status is VerificationStatus.HUMAN_VERIFIED
            stored_node = await uow.knowledge.get_node(node.id)
            assert stored_node is not None
            assert stored_node.status is VerificationStatus.REJECTED
            stored_relation = await uow.knowledge.get_relation(relation.id)
            assert stored_relation is not None
            assert stored_relation.status is VerificationStatus.NEEDS_REVISION
    finally:
        await store.aclose()


def test_knowledge_get_save_roundtrip_on_gel() -> None:
    asyncio.run(_test_knowledge_get_save_roundtrip_on_gel())


async def _test_knowledge_get_save_roundtrip_on_gel() -> None:
    store = _store()
    try:
        factory = GelUnitOfWorkFactory(store)
        suffix = uuid4()
        async with factory() as uow:
            project = Project(name=f"gel-save-{suffix}", slug=f"gel-save-{suffix}")
            await uow.sources.add_project(project)
            source = Source(project.id, SourceKind.PDF, "保存测试")
            await uow.sources.add_source(source)
            version = SourceVersion(source.id, 1, "save-h1", "save-k1")
            await uow.sources.add_version(version)
            block = ContentBlock(version.id, 0, "保存引用", "save-bh1", {"page": 1})
            await uow.sources.add_block(block)
            node = KnowledgeNode(project.id, "concept", "保存概念")
            await uow.knowledge.add_node(node)
            citation = Citation(block.id, "保存引用", {"page": 1})
            await uow.knowledge.add_citation(citation)
            claim = Claim(project.id, node.id, "保存声明", (citation,))
            await uow.knowledge.add_claim(claim)
            relation = Relation(
                project.id, "related_to", node.id, node.id, (citation.id,)
            )
            await uow.knowledge.add_relation(relation)
            await uow.commit()

        async with factory() as uow:
            await uow.knowledge.save_node(
                replace(
                    node,
                    properties={"reviewed": True},
                    status=VerificationStatus.HUMAN_VERIFIED,
                )
            )
            saved_node = await uow.knowledge.get_node(node.id)
            assert saved_node is not None
            assert saved_node.status is VerificationStatus.HUMAN_VERIFIED
            assert saved_node.properties == {"reviewed": True}

            await uow.knowledge.save_claim(
                replace(
                    claim,
                    status=VerificationStatus.MACHINE_CHECKED,
                    metadata={"compilation": {"task_id": str(uuid4())}},
                )
            )
            saved_claim = await uow.knowledge.get_claim(claim.id)
            assert saved_claim is not None
            assert saved_claim.status is VerificationStatus.MACHINE_CHECKED
            assert "compilation" in saved_claim.metadata
            assert saved_claim.citations[0].id == citation.id

            await uow.knowledge.save_relation(
                replace(
                    relation,
                    confidence=0.42,
                    status=VerificationStatus.NEEDS_REVISION,
                )
            )
            saved_relation = await uow.knowledge.get_relation(relation.id)
            assert saved_relation is not None
            # Gel schema stores confidence as float32 (SQLite keeps float64),
            # so exact float equality does not survive the round trip.
            assert saved_relation.confidence == pytest.approx(0.42)
            assert saved_relation.status is VerificationStatus.NEEDS_REVISION

            relation_type = await uow.knowledge.get_relation_type("related_to")
            assert relation_type is not None
            assert relation_type.directional is False
            await uow.commit()

        # missing-row save must raise DomainValidationError (one probe per UoW,
        # because a failed statement aborts the whole Gel transaction)
        probes = (
            (CandidateKind.NODE, node.id),
            (CandidateKind.CLAIM, claim.id),
            (CandidateKind.RELATION, relation.id),
        )
        for kind, _ in probes:
            async with factory() as uow:
                with pytest.raises(DomainValidationError):
                    if kind is CandidateKind.NODE:
                        await uow.knowledge.save_node(
                            KnowledgeNode(project.id, "concept", "ghost")
                        )
                    elif kind is CandidateKind.CLAIM:
                        await uow.knowledge.save_claim(replace(claim, id=uuid4()))
                    else:
                        await uow.knowledge.save_relation(
                            replace(relation, id=uuid4())
                        )
    finally:
        await store.aclose()


def test_job_queue_dequeue_retrying_on_gel() -> None:
    asyncio.run(_test_job_queue_dequeue_retrying_on_gel())


async def _test_job_queue_dequeue_retrying_on_gel() -> None:
    store = _store()
    try:
        factory = GelUnitOfWorkFactory(store)
        queue = GelJobQueue(store, poll_interval_seconds=0.01)
        # The dev database is shared and cumulative: earlier runs leave queued
        # jobs behind, so this test owns the Job table before asserting the
        # retrying/next_attempt_at eligibility predicate.
        await store.client.execute("delete Job")
        suffix = uuid4()
        now = datetime.now(UTC)
        past = Job(
            "pdf.parse",
            f"retry-past-{suffix}",
            {},
            status=JobStatus.RETRYING,
            next_attempt_at=now - timedelta(seconds=5),
        )
        null = Job(
            "pdf.parse",
            f"retry-null-{suffix}",
            {},
            status=JobStatus.RETRYING,
            next_attempt_at=None,
        )
        future = Job(
            "pdf.parse",
            f"retry-future-{suffix}",
            {},
            status=JobStatus.RETRYING,
            next_attempt_at=now + timedelta(hours=1),
        )
        async with factory() as uow:
            await uow.jobs.add(past)
            await uow.jobs.add(null)
            await uow.jobs.add(future)
            await uow.commit()

        # dequeue is only a view: claiming (status -> running) happens in
        # JobService.start_next, which is what the worker uses.
        service = JobService(factory, queue)
        first = await service.start_next(timeout_seconds=2)
        assert first is not None and first.id in {past.id, null.id}
        assert first.status is JobStatus.RUNNING
        second = await service.start_next(timeout_seconds=2)
        assert second is not None and second.id in {past.id, null.id}
        assert second.id != first.id
        # the future retry is not eligible yet
        assert await service.start_next(timeout_seconds=0.3) is None
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
