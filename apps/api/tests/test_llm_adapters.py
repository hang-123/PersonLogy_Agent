"""Tests for OpenAI-compatible LLM/embedding/rerank adapters (mocked HTTP)."""

import asyncio
import json
from uuid import uuid4

import httpx
import pytest
from personlogy.adapters.llm_openai import (
    OpenAICompatCompiler,
    OpenAICompatEmbeddingProvider,
    OpenAICompatReranker,
)
from personlogy.domain.knowledge.models import VerificationStatus
from personlogy.domain.source.models import ContentBlock, Source, SourceKind, SourceVersion
from personlogy.ports.retrieval import RetrievalHit
from personlogy.shared.errors import DomainValidationError

BASE = "https://llm.example.test/v1"
PROJECT_ID = uuid4()


def _blocks() -> tuple[ContentBlock, ...]:
    source = Source(PROJECT_ID, SourceKind.PDF, "测试")
    version = SourceVersion(source.id, 1, "h", "k")
    return (
        ContentBlock(
            source_version_id=version.id,
            ordinal=0,
            content="量子计算利用量子叠加与纠缠进行并行计算。",
            content_hash="b1",
            locator={"page": 1},
        ),
        ContentBlock(
            source_version_id=version.id,
            ordinal=1,
            content="量子比特是量子计算的基本单位。",
            content_hash="b2",
            locator={"page": 2},
        ),
    )


def _compile_payload() -> dict[str, object]:
    return {
        "nodes": [
            {"node_type": "concept", "title": "量子计算"},
            {"node_type": "concept", "title": "量子比特"},
        ],
        "claims": [
            {
                "statement": "量子计算利用量子叠加与纠缠进行并行计算。",
                "subject_title": "量子计算",
                "quote": "量子计算利用量子叠加与纠缠进行并行计算。",
                "confidence": 0.9,
            },
            {
                "statement": "量子比特是量子计算的基本单位。",
                "subject_title": "量子比特",
                "quote": "量子比特是量子计算的基本单位。",
                "confidence": 0.85,
            },
        ],
        "relations": [
            {
                "relation_type": "part_of",
                "source_title": "量子比特",
                "target_title": "量子计算",
                "quote": "量子比特是量子计算的基本单位。",
                "confidence": 0.8,
            }
        ],
    }


def test_openai_compiler_parses_bundle() -> None:
    blocks = _blocks()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": json.dumps(_compile_payload(), ensure_ascii=False)}}
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    compiler = OpenAICompatCompiler(
        base_url=BASE, api_key="test-key", model="test-model", transport=transport
    )
    bundle = compiler.compile(project_id=PROJECT_ID, blocks=blocks)

    assert bundle.model_name == "test-model"
    assert bundle.prompt_version == "p5-llm-openai-v1"
    assert len(bundle.nodes) == 2
    assert len(bundle.claims) == 2
    assert len(bundle.relations) == 1
    claim = bundle.claims[0]
    assert claim.subject_id == bundle.nodes[0].id
    assert claim.citations[0].content_block_id == blocks[0].id
    assert bundle.relations[0].relation_type == "part_of"
    # candidates stay unreviewed; governance applies machine_checked later
    assert claim.status is VerificationStatus.CANDIDATE


def test_openai_compiler_rejects_bad_output() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"nodes": "nope"}'}}]},
        )

    transport = httpx.MockTransport(handler)
    compiler = OpenAICompatCompiler(
        base_url=BASE, api_key="test-key", model="test-model", transport=transport
    )
    with pytest.raises(DomainValidationError):
        compiler.compile(project_id=PROJECT_ID, blocks=_blocks())


def test_openai_embedding_provider() -> None:
    async def run() -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"embedding": [0.1, 0.2, 0.3]},
                        {"embedding": [0.4, 0.5, 0.6]},
                    ]
                },
            )

        transport = httpx.MockTransport(handler)
        provider = OpenAICompatEmbeddingProvider(
            base_url=BASE, api_key="test-key", model="embed-model", transport=transport
        )
        vectors = await provider.embed(["a", "b"])

        assert len(vectors) == 2
        assert vectors[0].dimensions == 3
        assert vectors[0].model_name == "embed-model"
        assert vectors[0].values == (0.1, 0.2, 0.3)

    asyncio.run(run())


def test_openai_reranker_reorders_hits() -> None:
    hit_a = RetrievalHit(
        claim_id=uuid4(),
        project_id=PROJECT_ID,
        statement="结果 A",
        subject_id=uuid4(),
        subject_title="A",
        score=0.1,
        evidence=(),
        relations=(),
    )
    hit_b = RetrievalHit(
        claim_id=uuid4(),
        project_id=PROJECT_ID,
        statement="结果 B",
        subject_id=uuid4(),
        subject_title="B",
        score=0.2,
        evidence=(),
        relations=(),
    )

    async def run() -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"results": [{"index": 1, "relevance_score": 0.99}]})

        transport = httpx.MockTransport(handler)
        reranker = OpenAICompatReranker(
            base_url=BASE, api_key="test-key", model="rerank-model", transport=transport
        )
        ordered = await reranker.rerank(query="q", hits=(hit_a, hit_b), limit=10)

        assert len(ordered) == 1
        assert ordered[0].claim_id == hit_b.claim_id

    asyncio.run(run())


def test_reranker_returns_empty_for_no_hits() -> None:
    async def run() -> None:
        reranker = OpenAICompatReranker(
            base_url=BASE, api_key="test-key", model="rerank-model"
        )
        assert await reranker.rerank(query="q", hits=()) == ()

    asyncio.run(run())


def test_embedding_requires_model() -> None:
    with pytest.raises(DomainValidationError):
        OpenAICompatEmbeddingProvider(base_url=BASE, api_key="k", model="  ")
