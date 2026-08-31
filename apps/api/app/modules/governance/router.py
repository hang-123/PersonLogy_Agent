from uuid import UUID

from fastapi import APIRouter, status
from personlogy.domain.governance.models import ReviewTask, ReviewTaskStatus

from app.application.errors import ResourceNotFoundError
from app.modules.governance.schemas import ReviewDecisionRequest, ReviewTaskResponse
from app.runtime import governance_service

router = APIRouter(prefix="/review-tasks", tags=["governance"])


def to_response(task: ReviewTask) -> ReviewTaskResponse:
    return ReviewTaskResponse(
        id=task.id,
        run_id=task.run_id,
        candidate_id=task.candidate_id,
        candidate_kind=task.candidate_kind.value,
        status=task.status.value,
        reviewer_id=task.reviewer_id,
        reason=task.reason,
        version=task.version,
        before=task.before,
        after=task.after,
        created_at=task.created_at,
        reviewed_at=task.reviewed_at,
    )


@router.get("", response_model=list[ReviewTaskResponse])
async def list_review_tasks(limit: int = 100) -> list[ReviewTaskResponse]:
    tasks = await governance_service.list_review_tasks(limit=min(limit, 100))
    return [to_response(task) for task in tasks]


@router.get("/{task_id}", response_model=ReviewTaskResponse)
async def get_review_task(task_id: UUID) -> ReviewTaskResponse:
    task = await governance_service.get_review_task(task_id)
    if task is None:
        raise ResourceNotFoundError(f"review task {task_id} was not found")
    return to_response(task)


@router.post(
    "/{task_id}/decision",
    response_model=ReviewTaskResponse,
    status_code=status.HTTP_200_OK,
)
async def decide_review_task(
    task_id: UUID, request: ReviewDecisionRequest
) -> ReviewTaskResponse:
    try:
        task = await governance_service.decide_review_task(
            task_id,
            decision=ReviewTaskStatus(request.decision),
            reviewer_id=request.reviewer_id,
            reason=request.reason,
            expected_version=request.expected_version,
            changes=request.changes,
        )
    except ValueError as error:
        raise ResourceNotFoundError("review task decision is invalid") from error
    return to_response(task)
