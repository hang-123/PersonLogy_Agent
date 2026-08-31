"""Hybrid retrieval application service."""

from uuid import UUID

from personlogy.application.audit import append_audit_event
from personlogy.application.lineage import add_lineage_link
from personlogy.domain.audit import digest_for
from personlogy.ports.audit import AuditSink
from personlogy.ports.lineage import LineageStore
from personlogy.ports.retrieval import RetrievalHit, RetrievalReader
from personlogy.shared.errors import DomainValidationError
from personlogy.shared.trace import TraceContext


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
                metadata={**metadata, "error_digest": digest_for(str(error))},
            )
            raise
        await append_audit_event(
            self._audit_sink,
            event_type="retrieval.succeeded",
            status="succeeded",
            entity_type="retrieval_request",
            entity_id=request_id,
            context=context,
            metadata={**metadata, "result_count": len(hits)},
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


__all__ = ["RetrievalService"]
