"""Hybrid retrieval application service."""

from dataclasses import dataclass
from time import monotonic
from uuid import UUID

from personlogy.application.audit import append_audit_event
from personlogy.application.lineage import add_lineage_link
from personlogy.domain.audit import digest_for
from personlogy.ports.audit import AuditSink
from personlogy.ports.lineage import LineageStore
from personlogy.ports.retrieval import RetrievalHit, RetrievalReader
from personlogy.shared.errors import DomainValidationError
from personlogy.shared.trace import TraceContext


@dataclass(frozen=True, slots=True)
class RetrievalAnswer:
    project_id: UUID
    question: str
    answer: str
    hits: tuple[RetrievalHit, ...]
    uncertainty: tuple[str, ...]


class RetrievalService:
    def __init__(
        self,
        reader: RetrievalReader,
        audit_sink: AuditSink | None = None,
        lineage_store: LineageStore | None = None,
    ) -> None:
        self._reader = reader
        self._audit_sink = audit_sink
        self._lineage_store = lineage_store

    async def search(
        self,
        *,
        project_id: UUID,
        query: str,
        limit: int = 20,
        expand_relations: bool = False,
    ) -> tuple[RetrievalHit, ...]:
        if not query.strip():
            raise DomainValidationError("retrieval query is required")
        if not 1 <= limit <= 100:
            raise DomainValidationError("retrieval limit must be between 1 and 100")
        normalized_query = query.strip()
        context = TraceContext.current_or_root().child()
        request_id = context.span_id
        started_at = monotonic()
        metadata = {
            "project_id": str(project_id),
            "query_digest": digest_for(normalized_query),
            "limit": limit,
            "expand_relations": expand_relations,
            "retrieval_request_id": request_id,
        }
        await append_audit_event(
            self._audit_sink,
            event_type="retrieval.requested",
            status="requested",
            entity_type="retrieval_request",
            entity_id=request_id,
            context=context,
            metadata=metadata,
        )
        try:
            with context.activate():
                hits = await self._reader.search(
                    project_id=project_id,
                    query=normalized_query,
                    limit=limit,
                    expand_relations=expand_relations,
                )
        except Exception as error:
            await append_audit_event(
                self._audit_sink,
                event_type="retrieval.failed",
                status="failed",
                entity_type="retrieval_request",
                entity_id=request_id,
                context=context,
                reason_code="retrieval_failure",
                metadata={
                    **metadata,
                    "duration_ms": round((monotonic() - started_at) * 1000, 2),
                    "error_digest": digest_for(str(error)),
                },
            )
            raise
        await append_audit_event(
            self._audit_sink,
            event_type="retrieval.succeeded",
            status="succeeded",
            entity_type="retrieval_request",
            entity_id=request_id,
            context=context,
            metadata={
                **metadata,
                "duration_ms": round((monotonic() - started_at) * 1000, 2),
                "result_count": len(hits),
            },
        )
        for hit in hits:
            await add_lineage_link(
                self._lineage_store,
                project_id=project_id,
                from_type="retrieval_request",
                from_id=request_id,
                relation_type="returned_claim",
                to_type="claim",
                to_id=hit.claim_id,
            )
            for evidence in hit.evidence:
                await add_lineage_link(
                    self._lineage_store,
                    project_id=project_id,
                    from_type="retrieval_request",
                    from_id=request_id,
                    relation_type="used_evidence",
                    to_type="source_version",
                    to_id=evidence.source_version_id,
                )
        return hits

    async def answer(
        self,
        *,
        project_id: UUID,
        question: str,
        limit: int = 5,
        expand_relations: bool = False,
    ) -> RetrievalAnswer:
        normalized_question = question.strip()
        hits = await self.search(
            project_id=project_id,
            query=normalized_question,
            limit=limit,
            expand_relations=expand_relations,
        )
        if not hits:
            return RetrievalAnswer(
                project_id=project_id,
                question=normalized_question,
                answer="当前项目知识库中没有找到可直接支持该问题的已索引结论。",
                hits=(),
                uncertainty=("未找到匹配的已索引 Claim; 答案需要更多来源或先完成索引。",),
            )

        answer_lines = [f"基于当前项目检索到 {len(hits)} 条相关结论:"]
        uncertainty: list[str] = []
        for index, hit in enumerate(hits, start=1):
            answer_lines.append(f"{index}. {hit.statement}")
            if not hit.evidence:
                uncertainty.append(f"结论“{hit.statement}”没有返回 Citation, 无法完成来源核验。")
        return RetrievalAnswer(
            project_id=project_id,
            question=normalized_question,
            answer="\n".join(answer_lines),
            hits=hits,
            uncertainty=tuple(uncertainty),
        )


__all__ = ["RetrievalAnswer", "RetrievalService"]
