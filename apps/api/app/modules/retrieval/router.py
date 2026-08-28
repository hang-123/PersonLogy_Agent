from uuid import UUID

from fastapi import APIRouter, Header, Query, status
from personlogy.ports.retrieval import RetrievalHit

from app.modules.retrieval.schemas import (
    EvidenceResponse,
    RelationPathResponse,
    RetrievalHitResponse,
    RetrievalIndexResponse,
    RetrievalSearchResponse,
)
from app.runtime import job_service, retrieval_service

router = APIRouter(prefix="/retrieval", tags=["retrieval"])


def _to_response(hit: RetrievalHit) -> RetrievalHitResponse:
    return RetrievalHitResponse(
        claim_id=hit.claim_id,
        project_id=hit.project_id,
        statement=hit.statement,
        subject_id=hit.subject_id,
        subject_title=hit.subject_title,
        score=hit.score,
        evidence=[
            EvidenceResponse(
                citation_id=item.citation_id,
                quote=item.quote,
                source_id=item.source_id,
                source_title=item.source_title,
                source_version_id=item.source_version_id,
                locator=item.locator,
            )
            for item in hit.evidence
        ],
        relations=[
            RelationPathResponse(
                relation_id=item.relation_id,
                relation_type=item.relation_type,
                direction=item.direction,
                source_id=item.source_id,
                source_title=item.source_title,
                target_id=item.target_id,
                target_title=item.target_title,
            )
            for item in hit.relations
        ],
    )


@router.get("/search", response_model=RetrievalSearchResponse)
async def search(
    project_id: UUID,
    q: str = Query(min_length=1, max_length=500),
    limit: int = Query(default=20, ge=1, le=100),
    expand_relations: bool = False,
) -> RetrievalSearchResponse:
    hits = await retrieval_service.search(
        project_id=project_id,
        query=q,
        limit=limit,
        expand_relations=expand_relations,
    )
    return RetrievalSearchResponse(
        project_id=project_id,
        query=q,
        hits=[_to_response(hit) for hit in hits],
    )


@router.post(
    "/index",
    response_model=RetrievalIndexResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def rebuild_index(
    project_id: UUID,
    x_idempotency_key: str | None = Header(default=None, max_length=255),
) -> RetrievalIndexResponse:
    job = await job_service.submit(
        kind="retrieval.index",
        idempotency_key=x_idempotency_key or f"retrieval-index:{project_id}",
        payload={"project_id": str(project_id)},
    )
    return RetrievalIndexResponse(
        project_id=project_id,
        job_id=job.id,
        status=job.status,
        progress=job.progress,
        stage=job.stage,
    )
