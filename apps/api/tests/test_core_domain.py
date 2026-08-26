import asyncio
from uuid import uuid4

import pytest
from personlogy.adapters.memory import InMemoryStore, InMemoryUnitOfWorkFactory
from personlogy.domain.knowledge.models import Citation, Claim, KnowledgeNode
from personlogy.domain.relation.models import RelationType
from personlogy.domain.source.models import ContentBlock, Project, Source, SourceKind, SourceVersion
from personlogy.shared.errors import DomainValidationError


def test_claim_keeps_citation_in_transaction() -> None:
    asyncio.run(_test_claim_keeps_citation())


async def _test_claim_keeps_citation() -> None:
    store = InMemoryStore()
    factory = InMemoryUnitOfWorkFactory(store)
    project = Project("个人知识", "personal")
    source = Source(project.id, SourceKind.PDF, "说明文档")
    version = SourceVersion(source.id, 1, "hash-1", "sources/hash-1.pdf")
    block = ContentBlock(version.id, 0, "可引用原文", "block-hash", {"page": 1})
    node = KnowledgeNode(project.id, "concept", "知识点")
    citation = Citation(block.id, "可引用原文", {"page": 1})
    claim = Claim(project.id, node.id, "知识点有来源", (citation,))

    async with factory() as uow:
        await uow.sources.add_project(project)
        await uow.sources.add_source(source)
        await uow.sources.add_version(version)
        await uow.sources.add_block(block)
        await uow.knowledge.add_node(node)
        await uow.knowledge.add_citation(citation)
        await uow.knowledge.add_claim(claim)
        await uow.commit()

    assert store.claims[claim.id].citations[0].id == citation.id


def test_claim_without_citation_is_rejected() -> None:
    with pytest.raises(DomainValidationError, match="at least one citation"):
        Claim(uuid4(), uuid4(), "没有来源的结论", ())


def test_relation_type_can_be_registered() -> None:
    asyncio.run(_test_relation_type())


async def _test_relation_type() -> None:
    store = InMemoryStore()
    factory = InMemoryUnitOfWorkFactory(store)
    async with factory() as uow:
        await uow.knowledge.add_relation_type(RelationType("supports", "支持"))
        await uow.commit()
    assert "supports" in store.relation_types
