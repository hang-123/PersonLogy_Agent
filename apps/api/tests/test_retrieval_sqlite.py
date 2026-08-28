import asyncio
from pathlib import Path

from personlogy.adapters.sqlite import SQLiteStore, SQLiteUnitOfWorkFactory
from personlogy.adapters.sqlite_features import (
    SQLiteFeatureStore,
    SQLiteRetrievalIndexer,
    SQLiteRetrievalReader,
)
from personlogy.application.retrieval import RetrievalService
from personlogy.domain.knowledge.models import Citation, Claim, KnowledgeNode, VerificationStatus
from personlogy.domain.relation.models import Relation, RelationType
from personlogy.domain.source.models import ContentBlock, Project, Source, SourceKind, SourceVersion


def test_sqlite_retrieval_returns_evidence_and_one_hop_relations(tmp_path: Path) -> None:
    asyncio.run(_test_sqlite_retrieval_returns_evidence_and_one_hop_relations(tmp_path))


async def _test_sqlite_retrieval_returns_evidence_and_one_hop_relations(tmp_path: Path) -> None:
    database = tmp_path / "personlogy.sqlite3"
    store = SQLiteStore(database)
    features = SQLiteFeatureStore(database)
    factory = SQLiteUnitOfWorkFactory(store)
    project = Project("检索测试", "retrieval-test")
    source = Source(project.id, SourceKind.PDF, "检索来源")
    version = SourceVersion(source.id, 1, "source-hash", "sources/source.pdf")
    block = ContentBlock(version.id, 0, "用户偏好简洁方案。", "block-hash", {"page": 3})
    subject = KnowledgeNode(
        project.id,
        "preference",
        "回答风格",
        status=VerificationStatus.HUMAN_VERIFIED,
    )
    target = KnowledgeNode(
        project.id,
        "topic",
        "方案设计",
        status=VerificationStatus.HUMAN_VERIFIED,
    )
    citation = Citation(block.id, "用户偏好简洁方案。", {"page": 3})
    claim = Claim(
        project.id,
        subject.id,
        "用户偏好简洁方案",
        (citation,),
        status=VerificationStatus.HUMAN_VERIFIED,
    )
    relation_type = RelationType("related_to", "相关")
    relation = Relation(
        project.id,
        relation_type.key,
        subject.id,
        target.id,
        (citation.id,),
        status=VerificationStatus.HUMAN_VERIFIED,
    )

    async with factory() as uow:
        await uow.sources.add_project(project)
        await uow.sources.add_source(source)
        await uow.sources.add_version(version)
        await uow.sources.add_block(block)
        await uow.knowledge.add_node(subject)
        await uow.knowledge.add_node(target)
        await uow.knowledge.add_citation(citation)
        await uow.knowledge.add_claim(claim)
        await uow.knowledge.add_relation_type(relation_type)
        await uow.knowledge.add_relation(relation)
        await uow.commit()

    assert await SQLiteRetrievalIndexer(features).rebuild_project(project.id) == 1
    service = RetrievalService(SQLiteRetrievalReader(features))
    hits = await service.search(
        project_id=project.id,
        query="用户偏好简洁方案",
        expand_relations=True,
    )

    assert len(hits) == 1
    assert hits[0].claim_id == claim.id
    assert hits[0].evidence[0].source_title == "检索来源"
    assert hits[0].evidence[0].locator == {"page": 3}
    assert hits[0].relations[0].relation_type == "related_to"
    assert hits[0].relations[0].direction == "outgoing"


def test_sqlite_retrieval_is_project_scoped(tmp_path: Path) -> None:
    asyncio.run(_test_sqlite_retrieval_is_project_scoped(tmp_path))


async def _test_sqlite_retrieval_is_project_scoped(tmp_path: Path) -> None:
    database = tmp_path / "personlogy.sqlite3"
    SQLiteStore(database)
    features = SQLiteFeatureStore(database)
    reader = SQLiteRetrievalReader(features)
    assert await reader.search(project_id=Project("其他", "other").id, query="不存在") == ()
