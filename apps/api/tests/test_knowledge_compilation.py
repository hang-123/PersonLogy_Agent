import asyncio
import json
from pathlib import Path
from uuid import UUID

from personlogy.adapters.local_files import LocalFileStorage
from personlogy.adapters.sqlite import SQLiteJobQueue, SQLiteStore, SQLiteUnitOfWorkFactory
from personlogy.adapters.sqlite_lineage import SQLiteLineageStore
from personlogy.application.compilation import CompilationService, DocumentHeuristicCompiler
from personlogy.application.governance import GovernanceService
from personlogy.application.lineage import LineageService
from personlogy.application.orchestration import JobService
from personlogy.domain.governance.models import ReviewTaskStatus
from personlogy.domain.source.models import ContentBlock, Project, Source, SourceKind, SourceVersion


def test_heuristic_compiler_generates_source_bound_candidates() -> None:
    project = Project("编译测试", "compile-test")
    blocks = (
        ContentBlock(project.id, 0, "第一节\n知识编译", "hash-1", {"page": 1}),
        ContentBlock(project.id, 1, "第二节说明。补充内容。", "hash-2", {"page": 2}),
    )

    bundle = DocumentHeuristicCompiler().compile(project_id=project.id, blocks=blocks)

    assert len(bundle.nodes) == 2
    assert len(bundle.claims) == 2
    assert len(bundle.citations) == 2
    assert len(bundle.relations) == 1
    assert bundle.claims[0].citations[0].content_block_id == blocks[0].id
    assert bundle.relations[0].citation_ids == (bundle.citations[1].id,)
    assert bundle.okf["okf_version"] == "0.2"


def test_compilation_service_persists_candidates_and_okf(tmp_path: Path) -> None:
    asyncio.run(_test_compilation_service_persists_candidates_and_okf(tmp_path))


async def _test_compilation_service_persists_candidates_and_okf(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "personlogy.sqlite3")
    lineage = SQLiteLineageStore(tmp_path / "personlogy.sqlite3")
    factory = SQLiteUnitOfWorkFactory(store)
    project = Project("编译测试", "compile-test")
    source = Source(project.id, SourceKind.PDF, "测试 PDF")
    version = SourceVersion(source.id, 1, "pdf-hash", "projects/source.pdf")
    block = ContentBlock(version.id, 0, "知识编译应保留来源。", "block-hash", {"page": 1})
    async with factory() as uow:
        await uow.sources.add_project(project)
        await uow.sources.add_source(source)
        await uow.sources.add_version(version)
        await uow.sources.add_block(block)
        await uow.commit()

    queue = SQLiteJobQueue(store, poll_interval_seconds=0.01)
    job_service = JobService(factory, queue)
    service = CompilationService(
        factory,
        job_service,
        DocumentHeuristicCompiler(),
        LocalFileStorage(tmp_path / "files"),
        lineage_store=lineage,
    )
    job = await service.submit_for_version(
        project_id=project.id,
        source_version_id=version.id,
    )

    result = await service.process_compile_job(job)

    assert result.claim_count == 1
    assert result.citation_count == 1
    assert result.governance_status == "needs_review"
    assert result.review_task_count == 2
    assert result.okf_object_key.endswith(f"/{job.id}.okf.json")
    okf = json.loads((tmp_path / "files" / result.okf_object_key).read_text(encoding="utf-8"))
    assert okf["provenance"]["task_id"] == str(job.id)
    assert okf["claims"][0]["citation_ids"]

    async with factory() as uow:
        connection = uow._connection  # type: ignore[attr-defined]
        counts = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("knowledge_node", "citation", "claim")
        }
    assert counts == {"knowledge_node": 1, "citation": 1, "claim": 1}
    assert UUID(str(job.payload["source_version_id"])) == version.id
    source_trace = await LineageService(lineage).trace_source_version(
        project_id=project.id,
        source_version_id=version.id,
    )
    assert any(
        link.to_type == "claim" and link.relation_type == "generated"
        for link in source_trace.links
    )
    assert any(link.to_type == "review_task" for link in source_trace.links)

    governance = GovernanceService(factory)
    tasks = await governance.list_review_tasks()
    claim_task = next(task for task in tasks if task.candidate_kind.value == "claim")
    updated_task = await governance.decide_review_task(
        claim_task.id,
        decision=ReviewTaskStatus.APPROVED,
        reviewer_id="local-reviewer",
        reason="source is clear; allow the next writeback stage",
        expected_version=claim_task.version,
    )
    assert updated_task.status is ReviewTaskStatus.APPROVED

    async with factory() as uow:
        claim = await uow.knowledge.get_claim(claim_task.candidate_id)
    assert claim is not None
    assert claim.status.value == "human_verified"
