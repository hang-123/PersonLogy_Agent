import asyncio
import sqlite3
from pathlib import Path
from uuid import uuid4

from personlogy.adapters.sqlite import (
    SQLiteJobQueue,
    SQLiteStore,
    SQLiteUnitOfWorkFactory,
)
from personlogy.application.orchestration import JobService
from personlogy.domain.knowledge.models import Citation, Claim, KnowledgeNode
from personlogy.domain.source.models import ContentBlock, Project, Source, SourceKind, SourceVersion


def test_sqlite_job_survives_new_unit_of_work(tmp_path: Path) -> None:
    asyncio.run(_test_sqlite_job_survives_new_unit_of_work(tmp_path))


async def _test_sqlite_job_survives_new_unit_of_work(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "personlogy.sqlite3")
    factory = SQLiteUnitOfWorkFactory(store)
    service = JobService(factory, SQLiteJobQueue(store, poll_interval_seconds=0.01))

    submitted = await service.submit(
        kind="conversation.normalize",
        idempotency_key="conversation:sqlite:1",
        payload={"text": "本地持久化"},
    )
    reloaded = await service.get(submitted.id)

    assert reloaded is not None
    assert reloaded.id == submitted.id
    assert reloaded.payload == {"text": "本地持久化"}

    queued_id = await service._queue.dequeue(timeout_seconds=0.01)
    assert queued_id == submitted.id


def test_sqlite_repositories_keep_provenance_in_one_transaction(tmp_path: Path) -> None:
    asyncio.run(_test_sqlite_repositories_keep_provenance(tmp_path))


async def _test_sqlite_repositories_keep_provenance(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "personlogy.sqlite3")
    factory = SQLiteUnitOfWorkFactory(store)
    project = Project("本地知识", "local")
    source = Source(project.id, SourceKind.CONVERSATION, "对话导入")
    version = SourceVersion(source.id, 1, "hash-1", "sources/hash-1.json")
    block = ContentBlock(version.id, 0, "偏好简洁方案", "block-hash", {"message": 1})
    node = KnowledgeNode(project.id, "preference", "回答风格")
    citation = Citation(block.id, "偏好简洁方案", {"message": 1})
    claim = Claim(project.id, node.id, "用户偏好简洁方案", (citation,), confidence=0.9)

    async with factory() as uow:
        await uow.sources.add_project(project)
        await uow.sources.add_source(source)
        await uow.sources.add_version(version)
        await uow.sources.add_block(block)
        await uow.knowledge.add_node(node)
        await uow.knowledge.add_citation(citation)
        await uow.knowledge.add_claim(claim)
        await uow.commit()

    connection = sqlite3.connect(tmp_path / "personlogy.sqlite3")
    row = connection.execute(
        "SELECT statement FROM claim WHERE id = ?", (str(claim.id),)
    ).fetchone()
    connection.close()
    assert await factory().jobs.get(uuid4()) is None
    assert row[0] == "用户偏好简洁方案"
