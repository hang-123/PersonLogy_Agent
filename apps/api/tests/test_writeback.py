import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from personlogy.adapters.local_files import LocalFileStorage
from personlogy.adapters.sqlite import SQLiteStore, SQLiteUnitOfWorkFactory
from personlogy.adapters.sqlite_lineage import SQLiteLineageStore
from personlogy.application.writeback import LocalWritebackAuthorizer, WritebackService
from personlogy.domain.governance.models import (
    CandidateKind,
    GovernanceRun,
    GovernanceRunStatus,
    ReviewTask,
    ReviewTaskStatus,
)
from personlogy.domain.job import Job
from personlogy.domain.knowledge.models import Citation, Claim, KnowledgeNode, VerificationStatus
from personlogy.domain.source.models import ContentBlock, Project, Source, SourceKind, SourceVersion
from personlogy.domain.writeback.models import CandidateRef, WritebackRecord, WritebackStatus
from personlogy.shared.trace import TraceContext

from app.main import create_app
from app.modules.writebacks import router as writeback_router


def test_create_writeback_returns_accepted_record(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    candidate_id = uuid4()
    effects_job_id = uuid4()
    record = WritebackRecord(
        project_id=uuid4(),
        governance_run_id=uuid4(),
        schema_namespace="personlogy",
        schema_version=1,
        idempotency_key="api-writeback-1",
        request_digest="request-digest",
        candidate_digest="candidate-digest",
        candidates=(CandidateRef(candidate_id, CandidateKind.CLAIM, 2),),
        effects_job_id=effects_job_id,
        created_at=datetime.now(UTC),
    )
    effects_job = Job(
        kind="knowledge.writeback.effects",
        idempotency_key="knowledge-writeback-effects:test",
        payload={"writeback_id": str(record.id)},
        id=effects_job_id,
    )

    class FakeWritebackService:
        async def submit(self, **kwargs):  # type: ignore[no-untyped-def]
            assert kwargs["idempotency_key"] == "api-writeback-1"
            assert kwargs["candidates"][0].candidate_kind is CandidateKind.CLAIM
            return record, effects_job

    monkeypatch.setattr(writeback_router, "writeback_service", FakeWritebackService())
    response = TestClient(create_app()).post(
        "/v1/writebacks",
        headers={"X-Idempotency-Key": "api-writeback-1"},
        json={
            "project_id": str(record.project_id),
            "governance_run_id": str(record.governance_run_id),
            "candidates":[
                {
                    "candidate_id": str(candidate_id),
                    "candidate_kind": "claim",
                    "expected_review_version": 2,
                }
            ],
        },
    )

    assert response.status_code == 202
    assert response.json()["id"] == str(record.id)
    assert response.json()["status"] == WritebackStatus.EFFECTS_PENDING.value


def test_writeback_publishes_idempotently_and_completes_effects(tmp_path: Path) -> None:
    asyncio.run(_test_writeback_publishes_idempotently_and_completes_effects(tmp_path))


async def _test_writeback_publishes_idempotently_and_completes_effects(
    tmp_path: Path,
) -> None:
    store = SQLiteStore(tmp_path / "personlogy.sqlite3")
    factory = SQLiteUnitOfWorkFactory(store)
    project = Project("回写测试", "writeback-test")
    source = Source(project.id, SourceKind.PDF, "回写测试 PDF")
    version = SourceVersion(source.id, 1, "source-hash", "projects/source.pdf")
    block = ContentBlock(version.id, 0, "这是可审计的知识来源。", "block-hash", {"page": 1})
    node = KnowledgeNode(
        project.id,
        "concept",
        "知识来源",
        status=VerificationStatus.HUMAN_VERIFIED,
    )
    citation = Citation(block.id, "可审计的知识来源", {"page": 1})
    claim = Claim(
        project.id,
        node.id,
        "知识必须保留来源。",
        (citation,),
        status=VerificationStatus.HUMAN_VERIFIED,
    )
    run = GovernanceRun(
        project.id,
        project.id,
        "rules-1",
        GovernanceRunStatus.NEEDS_REVIEW,
        (node.id, claim.id),
    )
    task = ReviewTask(
        run.id,
        claim.id,
        CandidateKind.CLAIM,
        status=ReviewTaskStatus.APPROVED,
        reviewer_id="reviewer-1",
        reason="来源明确",
        before={"status": VerificationStatus.PENDING_REVIEW.value},
        after={"status": VerificationStatus.HUMAN_VERIFIED.value},
        version=2,
    )
    async with factory() as uow:
        await uow.sources.add_project(project)
        await uow.sources.add_source(source)
        await uow.sources.add_version(version)
        await uow.sources.add_block(block)
        await uow.knowledge.add_node(node)
        await uow.knowledge.add_citation(citation)
        await uow.knowledge.add_claim(claim)
        await uow.governance.add_run(run)
        await uow.governance.add_review_task(task)
        await uow.commit()

    lineage_store = SQLiteLineageStore(tmp_path / "personlogy.sqlite3")
    service = WritebackService(
        factory,
        LocalFileStorage(tmp_path / "files"),
        authorizer=LocalWritebackAuthorizer(environment="test"),
        lineage_store=lineage_store,
    )
    context = TraceContext.root(actor_type="user", actor_id="operator-1")
    with context.activate():
        record, effects_job = await service.submit(
            project_id=project.id,
            governance_run_id=run.id,
            candidates=(CandidateRef(claim.id, CandidateKind.CLAIM, task.version),),
            idempotency_key="writeback-test-1",
        )
        repeated, repeated_job = await service.submit(
            project_id=project.id,
            governance_run_id=run.id,
            candidates=(CandidateRef(claim.id, CandidateKind.CLAIM, task.version),),
            idempotency_key="writeback-test-1",
        )

    assert record.status is WritebackStatus.EFFECTS_PENDING
    assert repeated.id == record.id
    assert repeated_job.id == effects_job.id
    async with factory() as uow:
        published_claim = await uow.knowledge.get_claim(claim.id)
        stored_items = await uow.writebacks.list_items(record.id)
    assert published_claim is not None
    assert published_claim.status is VerificationStatus.READY_FOR_WRITEBACK
    assert len(stored_items) == 1

    class FailingStorage:
        async def put(self, key: str, content: bytes) -> None:
            del key, content
            raise OSError("object storage unavailable")

    failing_service = WritebackService(
        factory,
        FailingStorage(),  # type: ignore[arg-type]
        authorizer=LocalWritebackAuthorizer(environment="test"),
    )
    with pytest.raises(OSError):
        await failing_service.process_effects_job(effects_job)
    failed = await service.get(record.id)
    assert failed is not None
    assert failed.status is WritebackStatus.RETRYABLE_FAILED

    completed = await service.process_effects_job(effects_job)
    assert completed.status is WritebackStatus.COMPLETED
    assert completed.okf_object_key is not None
    okf = json.loads(
        (tmp_path / "files" / completed.okf_object_key).read_text(encoding="utf-8")
    )
    assert okf["provenance"]["writeback_id"] == str(record.id)
    assert okf["candidates"][0]["candidate_id"] == str(claim.id)
    lineage = await lineage_store.trace_entity(
        project_id=project.id,
        entity_type="writeback_record",
        entity_id=str(record.id),
    )
    assert {link.relation_type for link in lineage} >= {
        "derived_from",
        "publishes",
        "materialized_as",
    }
