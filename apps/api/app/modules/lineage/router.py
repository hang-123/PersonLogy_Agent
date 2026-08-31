from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from personlogy.application.lineage import LineageService, LineageTrace

from app.modules.lineage.schemas import LineageLinkResponse, LineageTraceResponse
from app.runtime import lineage_service

router = APIRouter(prefix="/lineage", tags=["lineage"])


def _to_response(trace: LineageTrace) -> LineageTraceResponse:
    return LineageTraceResponse(
        root_type=trace.root_type,
        root_id=trace.root_id,
        links=[
            LineageLinkResponse(
                link_id=link.link_id,
                project_id=link.project_id,
                from_type=link.from_type,
                from_id=link.from_id,
                relation_type=link.relation_type,
                to_type=link.to_type,
                to_id=link.to_id,
                created_at=link.created_at,
                metadata=dict(link.metadata),
            )
            for link in trace.links
        ],
    )


def _require_service() -> LineageService:
    if lineage_service is None:
        raise HTTPException(status_code=503, detail="lineage storage is not configured")
    return lineage_service


@router.get("/claims/{claim_id}", response_model=LineageTraceResponse)
async def trace_claim(
    claim_id: UUID,
    project_id: UUID,
    limit: int = Query(default=1000, ge=1, le=5000),
) -> LineageTraceResponse:
    trace = await _require_service().trace_claim(
        project_id=project_id,
        claim_id=claim_id,
        limit=limit,
    )
    return _to_response(trace)


@router.get("/source-versions/{source_version_id}", response_model=LineageTraceResponse)
async def trace_source_version(
    source_version_id: UUID,
    project_id: UUID,
    limit: int = Query(default=1000, ge=1, le=5000),
) -> LineageTraceResponse:
    trace = await _require_service().trace_source_version(
        project_id=project_id,
        source_version_id=source_version_id,
        limit=limit,
    )
    return _to_response(trace)


@router.get("/jobs/{job_id}", response_model=LineageTraceResponse)
async def trace_job(
    job_id: UUID,
    project_id: UUID,
    limit: int = Query(default=1000, ge=1, le=5000),
) -> LineageTraceResponse:
    trace = await _require_service().trace_job(
        project_id=project_id,
        job_id=job_id,
        limit=limit,
    )
    return _to_response(trace)


@router.get("/retrieval/{request_id}", response_model=LineageTraceResponse)
async def trace_retrieval(
    request_id: str,
    project_id: UUID,
    limit: int = Query(default=1000, ge=1, le=5000),
) -> LineageTraceResponse:
    trace = await _require_service().trace_retrieval(
        project_id=project_id,
        request_id=request_id,
        limit=limit,
    )
    return _to_response(trace)
