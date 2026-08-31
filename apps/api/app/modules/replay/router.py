from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from personlogy.application.replay import ReplayService
from personlogy.domain.replay import ReplayComparison, ReplayPlan, ReplayVersionSet

from app.modules.replay.schemas import (
    ReplayApprovalResponse,
    ReplayCompareRequest,
    ReplayComparisonResponse,
    ReplayPlanCreateRequest,
    ReplayPlanDetailResponse,
    ReplayPlanResponse,
    ReplayVersionResponse,
)
from app.runtime import replay_service

router = APIRouter(prefix="/replay", tags=["replay"])


def _require_service() -> ReplayService:
    if replay_service is None:
        raise HTTPException(status_code=503, detail="replay storage is not configured")
    return replay_service


def _version(version: ReplayVersionSet) -> ReplayVersionResponse:
    return ReplayVersionResponse(
        schema_version=version.schema_version,
        compiler_version=version.compiler_version,
        embedding_version=version.embedding_version,
        index_version=version.index_version,
    )


def _plan(plan: ReplayPlan) -> ReplayPlanResponse:
    return ReplayPlanResponse(
        plan_id=plan.plan_id,
        project_id=plan.project_id,
        source_version_id=plan.source_version_id,
        parent_trace_id=plan.parent_trace_id,
        parent_job_id=plan.parent_job_id,
        baseline_input_content_hash=plan.baseline_input_content_hash,
        baseline_versions=_version(plan.baseline_versions),
        target_input_content_hash=plan.target_input_content_hash,
        target_versions=_version(plan.target_versions),
        status=plan.status,
        replay_job_id=plan.replay_job_id,
        created_at=plan.created_at,
        approved_at=plan.approved_at,
    )


def _comparison(comparison: ReplayComparison) -> ReplayComparisonResponse:
    return ReplayComparisonResponse(
        comparison_id=comparison.comparison_id,
        project_id=comparison.project_id,
        plan_id=comparison.plan_id,
        source_version_id=comparison.source_version_id,
        replay_job_id=comparison.replay_job_id,
        difference_dimensions=list(comparison.difference_dimensions),
        output_changed=comparison.output_changed,
        original_output_digest=comparison.original_output_digest,
        replay_output_digest=comparison.replay_output_digest,
        status=comparison.status,
        created_at=comparison.created_at,
    )


@router.post("/plans", response_model=ReplayPlanResponse, status_code=status.HTTP_201_CREATED)
async def create_replay_plan(request: ReplayPlanCreateRequest) -> ReplayPlanResponse:
    plan = await _require_service().create_plan(
        project_id=request.project_id,
        source_version_id=request.source_version_id,
        parent_job_id=request.parent_job_id,
        target_schema_version=request.target_schema_version,
        target_compiler_version=request.target_compiler_version,
        target_embedding_version=request.target_embedding_version,
        target_index_version=request.target_index_version,
    )
    return _plan(plan)


@router.get("/plans/{plan_id}", response_model=ReplayPlanDetailResponse)
async def get_replay_plan(
    plan_id: UUID,
    project_id: UUID,
    limit: int = Query(default=100, ge=1, le=1000),
) -> ReplayPlanDetailResponse:
    service = _require_service()
    plan = await service.get_plan(plan_id, project_id=project_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="replay plan was not found")
    comparisons = await service.list_comparisons(plan_id, limit=limit)
    return ReplayPlanDetailResponse(
        plan=_plan(plan),
        comparisons=[_comparison(item) for item in comparisons],
    )


@router.post("/plans/{plan_id}/approve", response_model=ReplayApprovalResponse)
async def approve_replay_plan(plan_id: UUID, project_id: UUID) -> ReplayApprovalResponse:
    service = _require_service()
    job = await service.approve(plan_id, project_id=project_id)
    plan = await service.get_plan(plan_id, project_id=project_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="replay plan was not found")
    return ReplayApprovalResponse(
        plan_id=plan.plan_id,
        job_id=job.id,
        trace_id=job.trace_id,
        parent_trace_id=plan.parent_trace_id,
        parent_job_id=plan.parent_job_id,
        status=job.status,
    )


@router.post(
    "/plans/{plan_id}/compare",
    response_model=ReplayComparisonResponse,
    status_code=status.HTTP_201_CREATED,
)
async def compare_replay(
    plan_id: UUID,
    project_id: UUID,
    request: ReplayCompareRequest,
) -> ReplayComparisonResponse:
    comparison = await _require_service().compare(
        plan_id,
        project_id=project_id,
        original_output_digest=request.original_output_digest,
        replay_output_digest=request.replay_output_digest,
    )
    return _comparison(comparison)


__all__ = ["router"]
