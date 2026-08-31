import asyncio
from pathlib import Path

import pytest
from personlogy.adapters.sqlite import SQLiteJobQueue, SQLiteStore, SQLiteUnitOfWorkFactory
from personlogy.adapters.sqlite_audit import SQLiteRecordStore
from personlogy.adapters.sqlite_lineage import SQLiteLineageStore
from personlogy.adapters.sqlite_replay import SQLiteReplayStore
from personlogy.application.lineage import LineageService
from personlogy.application.orchestration import JobService
from personlogy.application.replay import ReplayService
from personlogy.domain.job import Job, JobStatus
from personlogy.domain.source.models import Project, Source, SourceKind, SourceVersion
from personlogy.shared.errors import DomainValidationError


def test_replay_plan_approval_creates_isolated_job_and_candidate_diff(tmp_path: Path) -> None:
    asyncio.run(_test_replay_plan_approval_creates_isolated_job_and_candidate_diff(tmp_path))


async def _test_replay_plan_approval_creates_isolated_job_and_candidate_diff(
    tmp_path: Path,
) -> None:
    database = tmp_path / "personlogy.sqlite3"
    store = SQLiteStore(database)
    audit = SQLiteRecordStore(database)
    lineage = SQLiteLineageStore(database)
    replay_store = SQLiteReplayStore(database)
    factory = SQLiteUnitOfWorkFactory(store)
    project = Project("回放项目", "replay-project")
    source = Source(project.id, SourceKind.PDF, "回放来源")
    version = SourceVersion(source.id, 1, "input-hash-v1", "sources/replay.pdf")
    parent = Job(
        "knowledge.compile",
        "parent-compile-1",
        {
            "project_id": str(project.id),
            "compiler": "compiler-v1",
            "prompt_version": "prompt-v1",
            "schema_version": "schema-v1",
            "embedding_version": "embedding-v1",
            "index_version": 1,
        },
        trace_id="parent-trace-1",
    )
    async with factory() as uow:
        await uow.sources.add_project(project)
        await uow.sources.add_source(source)
        await uow.sources.add_version(version)
        await uow.jobs.add(parent)
        await uow.commit()

    job_service = JobService(
        factory,
        SQLiteJobQueue(store, poll_interval_seconds=0.01),
        audit_sink=audit,
    )
    service = ReplayService(
        factory,
        job_service,
        replay_store,
        audit_sink=audit,
        lineage_store=lineage,
    )
    plan = await service.create_plan(
        project_id=project.id,
        source_version_id=version.id,
        parent_job_id=parent.id,
        target_schema_version="schema-v2",
        target_compiler_version="compiler-v2",
        target_embedding_version="embedding-v2",
        target_index_version=2,
    )
    assert plan.status.value == "proposed"
    assert plan.replay_job_id is None
    assert await job_service.list() == [parent]

    replay_job = await service.approve(plan.plan_id, project_id=project.id)
    assert replay_job.id != parent.id
    assert replay_job.trace_id != parent.trace_id
    assert replay_job.status is JobStatus.QUEUED
    assert replay_job.payload["parent_job_id"] == str(parent.id)
    assert replay_job.payload["parent_trace_id"] == parent.trace_id
    assert replay_job.payload["replay_plan_id"] == str(plan.plan_id)

    approved = await service.get_plan(plan.plan_id, project_id=project.id)
    assert approved is not None
    assert approved.status.value == "queued"
    assert approved.replay_job_id == replay_job.id
    job_events = await audit.list(entity_id=str(replay_job.id))
    submitted = next(event for event in job_events if event.event_type == "job.submitted")
    assert submitted.metadata["parent_job_id"] == str(parent.id)
    assert submitted.metadata["parent_trace_id"] == parent.trace_id

    comparison = await service.compare(
        plan.plan_id,
        project_id=project.id,
        original_output={"candidate_count": 1},
        replay_output={"candidate_count": 2},
    )
    assert comparison.output_changed is True
    assert set(comparison.difference_dimensions) == {
        "schema",
        "compiler",
        "embedding",
        "index",
        "output",
    }
    completed = await service.get_plan(plan.plan_id, project_id=project.id)
    assert completed is not None
    assert completed.status.value == "completed"

    async with factory() as uow:
        original = await uow.jobs.get(parent.id)
        jobs = await uow.jobs.list(limit=10)
    assert original is not None
    assert original.status is JobStatus.QUEUED
    assert {item.id for item in jobs} == {parent.id, replay_job.id}

    trace = await LineageService(lineage).trace_job(
        project_id=project.id,
        job_id=replay_job.id,
    )
    assert any(link.to_type == "replay_plan" for link in trace.links)
    assert any(link.to_type == "replay_comparison" for link in trace.links)


def test_replay_plan_rejects_cross_project_source_version(tmp_path: Path) -> None:
    asyncio.run(_test_replay_plan_rejects_cross_project_source_version(tmp_path))


async def _test_replay_plan_rejects_cross_project_source_version(tmp_path: Path) -> None:
    database = tmp_path / "personlogy.sqlite3"
    store = SQLiteStore(database)
    replay_store = SQLiteReplayStore(database)
    factory = SQLiteUnitOfWorkFactory(store)
    project = Project("项目 A", "replay-project-a")
    other_project = Project("项目 B", "replay-project-b")
    source = Source(project.id, SourceKind.PDF, "来源 A")
    version = SourceVersion(source.id, 1, "hash-a", "sources/a.pdf")
    async with factory() as uow:
        await uow.sources.add_project(project)
        await uow.sources.add_project(other_project)
        await uow.sources.add_source(source)
        await uow.sources.add_version(version)
        await uow.commit()

    service = ReplayService(
        factory,
        JobService(factory, SQLiteJobQueue(store)),
        replay_store,
    )
    with pytest.raises(DomainValidationError, match="does not belong"):
        await service.create_plan(
            project_id=other_project.id,
            source_version_id=version.id,
        )
