"""OpenAI-compatible LLM adapters for knowledge compilation, embeddings and reranking.

These adapters talk to any endpoint that speaks the OpenAI HTTP surface:
``/v1/chat/completions`` (compilation), ``/v1/embeddings`` (embeddings) and
``/v1/rerank`` (reranking, Cohere-compatible payload).

Configuration is injected at construction time (see ``apps/api/app/core/config.py``
and ``runtime.py``); no credentials are hard-coded here.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

import httpx

from personlogy.domain.knowledge.models import Citation, Claim, KnowledgeNode
from personlogy.domain.relation.models import Relation, RelationType
from personlogy.domain.source.models import ContentBlock
from personlogy.ports.compilation import CompilationBundle
from personlogy.ports.retrieval import EmbeddingVector, RetrievalHit
from personlogy.shared.errors import DomainValidationError

DEFAULT_TIMEOUT_SECONDS = 60.0

_INITIAL_RELATION_TYPES = (
    "is_a",
    "part_of",
    "depends_on",
    "supports",
    "contradicts",
    "related_to",
    "derived_from",
)

_COMPILE_SYSTEM_PROMPT = """\
你是知识库编译引擎。输入是文档内容块（含页码定位），输出必须是一段 JSON，\
表示从内容中提取的结构化知识。只输出 JSON，不要 Markdown 代码块，不要解释。\
JSON 结构：
{
  "nodes": [{"node_type": "concept", "title": "概念名"}],
  "claims": [
    {
      "statement": "断言内容",
      "subject_title": "所属概念标题（必须对应 nodes 中的 title）",
      "quote": "原文引用（必须来自输入内容块）",
      "confidence": 0.0~1.0
    }
  ],
  "relations": [
    {
      "relation_type": "is_a|part_of|depends_on|supports|contradicts|related_to|derived_from",
      "source_title": "起点概念标题",
      "target_title": "终点概念标题",
      "quote": "原文引用",
      "confidence": 0.0~1.0
    }
  ]
}
规则：claims 和 relations 的 quote 必须逐字来自输入内容块；不臆造；无法确定就不输出。\
"""


def _auth_headers(api_key: str) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _completion_request(
    *,
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    temperature: float,
    timeout: float,
    max_tokens: int = 8192,
    transport: httpx.BaseTransport | None = None,
) -> dict[str, object]:
    url = base_url.rstrip("/") + "/chat/completions"
    payload: dict[str, object] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if transport is not None:
        response = httpx.Client(transport=transport, base_url=base_url).post(
            url,
            headers=_auth_headers(api_key),
            json=payload,
            timeout=timeout,
        )
    else:
        response = httpx.post(
            url,
            headers=_auth_headers(api_key),
            json=payload,
            timeout=timeout,
        )
    response.raise_for_status()
    try:
        data = cast(dict[str, Any], response.json())
    except ValueError as error:
        raise DomainValidationError("LLM completion response is not valid JSON") from error
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as error:
        raise DomainValidationError(
            "LLM completion response missing choices[0].message.content"
        ) from error
    if isinstance(content, str):
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as error:
            raise DomainValidationError("LLM compilation output is not valid JSON") from error
    else:
        parsed = content
    if not isinstance(parsed, dict):
        raise DomainValidationError("LLM compilation output is not a JSON object")
    return cast(dict[str, object], parsed)


class OpenAICompatCompiler:
    """Compile content blocks into candidates using an OpenAI-compatible chat model."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        temperature: float = 0.2,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not base_url.strip() or not model.strip():
            raise DomainValidationError("LLM base_url and model are required")
        self._base_url = base_url
        self._api_key = api_key
        self._model = model
        self._timeout = timeout_seconds
        self._temperature = temperature
        self._transport = transport
        self.model_name = model

    prompt_version = "p5-llm-openai-v1"
    model_name: str = "openai-compatible"

    def compile(self, *, project_id: UUID, blocks: tuple[ContentBlock, ...]) -> CompilationBundle:
        block_texts = "\n\n".join(
            f"[块 {block.ordinal} | 页码 {_page(block.locator)}]\n{block.content}"
            for block in blocks
        )
        user_prompt = f"以下是文档内容块：\n\n{block_texts}\n\n请按系统规则提取知识 JSON。"
        parsed = _completion_request(
            base_url=self._base_url,
            api_key=self._api_key,
            model=self._model,
            messages=[
                {"role": "system", "content": _COMPILE_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=self._temperature,
            timeout=self._timeout,
            transport=self._transport,
        )
        return _parse_bundle(parsed, project_id=project_id, blocks=blocks, model=self._model)


class OpenAICompatEmbeddingProvider:
    """Embed texts using an OpenAI-compatible embeddings endpoint."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not base_url.strip() or not model.strip():
            raise DomainValidationError("embedding base_url and model are required")
        self._base_url = base_url
        self._api_key = api_key
        self._model = model
        self._timeout = timeout_seconds
        self._transport = transport

    @property
    def model_name(self) -> str:
        return self._model

    model_version = "openai-compatible-v1"

    async def embed(self, texts: Sequence[str]) -> tuple[EmbeddingVector, ...]:
        if not texts:
            return ()
        url = self._base_url.rstrip("/") + "/embeddings"
        if self._transport is not None:
            client = httpx.AsyncClient(transport=self._transport, timeout=self._timeout)
        else:
            client = httpx.AsyncClient(timeout=self._timeout)
        async with client:
            response = await client.post(
                url,
                headers=_auth_headers(self._api_key),
                json={"model": self._model, "input": list(texts)},
            )
        response.raise_for_status()
        try:
            data = cast(dict[str, Any], response.json())
        except ValueError as error:
            raise DomainValidationError("embedding response is not valid JSON") from error
        items = data.get("data")
        if not isinstance(items, list) or not items:
            raise DomainValidationError("embedding response missing data[]")
        vectors: list[EmbeddingVector] = []
        for item in items:
            if not isinstance(item, dict):
                raise DomainValidationError("embedding response entry must be an object")
            values = item.get("embedding")
            if not isinstance(values, list) or not values:
                raise DomainValidationError("embedding response entry missing embedding[]")
            try:
                converted = tuple(float(value) for value in values)
            except (TypeError, ValueError) as error:
                raise DomainValidationError(
                    "embedding response contains a non-numeric value"
                ) from error
            vectors.append(
                EmbeddingVector(
                    model_name=self._model,
                    model_version=self.model_version,
                    values=converted,
                )
            )
        return tuple(vectors)


class OpenAICompatReranker:
    """Rerank retrieval hits using a Cohere-compatible /rerank endpoint."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not base_url.strip() or not model.strip():
            raise DomainValidationError("rerank base_url and model are required")
        self._base_url = base_url
        self._api_key = api_key
        self._model = model
        self._timeout = timeout_seconds
        self._transport = transport

    @property
    def model_name(self) -> str:
        return self._model

    model_version = "cohere-compatible-v1"

    async def rerank(
        self,
        *,
        query: str,
        hits: Sequence[RetrievalHit],
        limit: int = 20,
    ) -> tuple[RetrievalHit, ...]:
        if not hits:
            return ()
        url = self._base_url.rstrip("/") + "/rerank"
        documents = [hit.statement for hit in hits]
        if self._transport is not None:
            client = httpx.AsyncClient(transport=self._transport, timeout=self._timeout)
        else:
            client = httpx.AsyncClient(timeout=self._timeout)
        async with client:
            response = await client.post(
                url,
                headers=_auth_headers(self._api_key),
                json={"model": self._model, "query": query, "documents": documents},
            )
        response.raise_for_status()
        try:
            data = cast(dict[str, Any], response.json())
        except ValueError as error:
            raise DomainValidationError("rerank response is not valid JSON") from error
        results = data.get("results")
        if not isinstance(results, list):
            raise DomainValidationError("rerank response missing results[]")
        ordered: list[RetrievalHit] = []
        for result in results:
            if not isinstance(result, dict):
                raise DomainValidationError("rerank response entry must be an object")
            index = result.get("index")
            if not isinstance(index, int) or not 0 <= index < len(hits):
                raise DomainValidationError("rerank response entry has an invalid index")
            ordered.append(hits[index])
        return tuple(ordered[:limit])


def _page(locator: dict[str, object]) -> object:
    return locator.get("page", locator.get("ordinal", "?"))


def _parse_bundle(
    parsed: dict[str, object],
    *,
    project_id: UUID,
    blocks: tuple[ContentBlock, ...],
    model: str,
) -> CompilationBundle:
    nodes_raw = parsed.get("nodes")
    claims_raw = parsed.get("claims")
    relations_raw = parsed.get("relations")
    if not isinstance(nodes_raw, list) or not isinstance(claims_raw, list):
        raise DomainValidationError("LLM output missing nodes[] or claims[]")

    nodes: list[KnowledgeNode] = []
    title_to_node: dict[str, KnowledgeNode] = {}
    for item in nodes_raw:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()
        node_type = str(item.get("node_type", "concept")).strip()
        if not title:
            continue
        node = KnowledgeNode(
            project_id=project_id,
            node_type=node_type,
            title=title,
            properties={"extraction": "llm", "model": model},
        )
        nodes.append(node)
        title_to_node.setdefault(title, node)

    citations: list[Citation] = []
    claims: list[Claim] = []
    for item in claims_raw:
        if not isinstance(item, dict):
            continue
        statement = str(item.get("statement", "")).strip()
        subject_title = str(item.get("subject_title", "")).strip()
        quote = str(item.get("quote", "")).strip()
        subject = title_to_node.get(subject_title)
        match = _find_block(blocks, quote)
        if not statement or subject is None or match is None:
            continue
        block, quote_start, quote_end = match
        citation = Citation(
            content_block_id=block.id,
            quote=quote,
            locator=dict(block.locator),
            metadata={
                "extraction": "llm",
                "model": model,
                "quote_start": quote_start,
                "quote_end": quote_end,
            },
        )
        citations.append(citation)
        claims.append(
            Claim(
                project_id=project_id,
                subject_id=subject.id,
                statement=statement,
                citations=(citation,),
                confidence=_optional_confidence(item.get("confidence")),
                metadata={"extraction": "llm", "model": model},
            )
        )

    relation_types = [
        RelationType(key=key, label=key, description="LLM extracted", directional=True)
        for key in _INITIAL_RELATION_TYPES
    ]
    relations: list[Relation] = []
    if isinstance(relations_raw, list):
        for item in relations_raw:
            if not isinstance(item, dict):
                continue
            relation_type = str(item.get("relation_type", "")).strip()
            source_title = str(item.get("source_title", "")).strip()
            target_title = str(item.get("target_title", "")).strip()
            quote = str(item.get("quote", "")).strip()
            source = title_to_node.get(source_title)
            target = title_to_node.get(target_title)
            match = _find_block(blocks, quote)
            if (
                relation_type not in _INITIAL_RELATION_TYPES
                or source is None
                or target is None
                or match is None
            ):
                continue
            block, quote_start, quote_end = match
            citation = Citation(
                content_block_id=block.id,
                quote=quote,
                locator=dict(block.locator),
                metadata={
                    "extraction": "llm",
                    "model": model,
                    "quote_start": quote_start,
                    "quote_end": quote_end,
                    "evidence_for": "relation",
                },
            )
            citations.append(citation)
            relations.append(
                Relation(
                    project_id=project_id,
                    relation_type=relation_type,
                    source_id=source.id,
                    target_id=target.id,
                    citation_ids=(citation.id,),
                    properties={"extraction": "llm", "model": model},
                    confidence=_optional_confidence(item.get("confidence")),
                )
            )

    generated_at = datetime.now(UTC)
    okf: dict[str, object] = {
        "okf_version": "0.2",
        "generated_at": generated_at.isoformat(),
        "provenance": {
            "model": model,
            "model_name": model,
            "prompt_version": "p5-llm-openai-v1",
            "extraction": "llm",
            "generated_at": datetime.now(UTC).isoformat(),
        },
        "bundle_type": "knowledge_candidates",
        "project_id": str(project_id),
        "source_version_id": str(blocks[0].source_version_id) if blocks else None,
        "concepts": [
            {
                "id": str(node.id),
                "type": node.node_type,
                "title": node.title,
                "properties": node.properties,
                "status": node.status.value,
            }
            for node in nodes
        ],
        "citations": [
            {
                "id": str(citation.id),
                "content_block_id": str(citation.content_block_id),
                "quote": citation.quote,
                "locator": citation.locator,
                "metadata": citation.metadata,
            }
            for citation in citations
        ],
        "claims": [
            {
                "id": str(claim.id),
                "subject_id": str(claim.subject_id),
                "statement": claim.statement,
                "confidence": claim.confidence,
                "status": claim.status.value,
                "citation_ids": [str(item.id) for item in claim.citations],
            }
            for claim in claims
        ],
        "relations": [
            {
                "relation_type": relation.relation_type,
                "id": str(relation.id),
                "source_id": str(relation.source_id),
                "target_id": str(relation.target_id),
                "confidence": relation.confidence,
                "citation_ids": [str(item) for item in relation.citation_ids],
                "properties": relation.properties,
            }
            for relation in relations
        ],
    }
    return CompilationBundle(
        nodes=tuple(nodes),
        citations=tuple(citations),
        claims=tuple(claims),
        relations=tuple(relations),
        relation_types=tuple(relation_types),
        okf=okf,
        prompt_version="p5-llm-openai-v1",
        model_name=model,
        generated_at=generated_at,
    )


def _find_block(
    blocks: tuple[ContentBlock, ...], quote: str
) -> tuple[ContentBlock, int, int] | None:
    """Find the exact source block and offsets for a non-empty quote."""
    cleaned = quote.strip()
    if not cleaned:
        return None
    for block in blocks:
        start = block.content.find(cleaned)
        if start >= 0:
            return block, start, start + len(cleaned)
    return None


def _optional_confidence(value: object) -> float | None:
    if isinstance(value, (int, float)) and 0 <= float(value) <= 1:
        return float(value)
    return None


__all__ = [
    "OpenAICompatCompiler",
    "OpenAICompatEmbeddingProvider",
    "OpenAICompatReranker",
]
