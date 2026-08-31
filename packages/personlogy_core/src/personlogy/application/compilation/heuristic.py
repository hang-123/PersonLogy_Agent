"""Deterministic PDF-first compiler used until an LLM provider is available."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from uuid import UUID

from personlogy.domain.knowledge.models import Citation, Claim, KnowledgeNode
from personlogy.domain.relation.models import Relation, RelationType
from personlogy.domain.source.models import ContentBlock
from personlogy.ports.compilation import CompilationBundle


class DocumentHeuristicCompiler:
    """Turn parsed document blocks into reviewable, source-bound candidates.

    This is intentionally conservative: it never publishes knowledge and marks
    adjacency relations as weak candidates. A future LLM compiler can implement
    the same ``KnowledgeCompiler`` port and replace this class at composition time.
    """

    prompt_version = "p5-heuristic-v1"
    model_name = "local-heuristic"

    def compile(
        self, *, project_id: UUID, blocks: tuple[ContentBlock, ...]
    ) -> CompilationBundle:
        nodes: list[KnowledgeNode] = []
        citations: list[Citation] = []
        claims: list[Claim] = []
        relations: list[Relation] = []
        relation_types: list[RelationType] = []

        for block in blocks:
            title = _concept_title(block.content, block.locator)
            node = KnowledgeNode(
                project_id=project_id,
                node_type="concept",
                title=title,
                properties={
                    "extraction": "heuristic",
                    "source_block_id": str(block.id),
                },
            )
            citation = Citation(
                content_block_id=block.id,
                quote=_quote(block.content),
                locator=block.locator,
                metadata={"extraction": "heuristic"},
            )
            claim = Claim(
                project_id=project_id,
                subject_id=node.id,
                statement=_claim_statement(block.content),
                citations=(citation,),
                confidence=0.35,
                metadata={"extraction": "heuristic"},
            )
            nodes.append(node)
            citations.append(citation)
            claims.append(claim)

        if len(nodes) > 1:
            relation_types.append(
                RelationType(
                    key="related_to",
                    label="相关",
                    description="相邻文档片段之间的弱关联候选，需人工复核。",
                )
            )
            for previous, current, citation in zip(
                nodes, nodes[1:], citations[1:], strict=False
            ):
                relations.append(
                    Relation(
                        project_id=project_id,
                        relation_type="related_to",
                        source_id=previous.id,
                        target_id=current.id,
                        citation_ids=(citation.id,),
                        properties={
                            "candidate_reason": "adjacent_document_blocks",
                            "status": "candidate",
                        },
                        confidence=0.2,
                        metadata={"extraction": "heuristic"},
                    )
                )

        generated_at = datetime.now(UTC)
        source_version_id = str(blocks[0].source_version_id) if blocks else None
        okf: dict[str, object] = {
            "okf_version": "0.2",
            "bundle_type": "knowledge_candidates",
            "project_id": str(project_id),
            "source_version_id": source_version_id,
            "generated_at": generated_at.isoformat(),
            "provenance": {
                "model_name": self.model_name,
                "prompt_version": self.prompt_version,
                "mode": "heuristic",
            },
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
                    "id": str(relation.id),
                    "relation_type": relation.relation_type,
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
            prompt_version=self.prompt_version,
            model_name=self.model_name,
            generated_at=generated_at,
        )


def _concept_title(content: str, locator: dict[str, object]) -> str:
    first_line = content.splitlines()[0].strip()
    if locator.get("block_type") == "heading":
        return _truncate(first_line, 120)
    sentence = re.split(r"(?<=[\u3002\uff01\uff1f.!?])\s*", content, maxsplit=1)[0].strip()
    return _truncate(sentence or first_line, 80)


def _claim_statement(content: str) -> str:
    normalized = " ".join(content.split())
    return _truncate(normalized, 500)


def _quote(content: str) -> str:
    return _truncate(" ".join(content.split()), 1000)


def _truncate(value: str, limit: int) -> str:
    return value if len(value) <= limit else f"{value[: limit - 1].rstrip()}…"
