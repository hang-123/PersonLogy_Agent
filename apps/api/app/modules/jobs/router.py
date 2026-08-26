from uuid import UUID

from fastapi import APIRouter, Header, status
from personlogy.domain.job import Job

from app.application.errors import ResourceNotFoundError
from app.modules.jobs.schemas import JobCreateRequest, JobResponse
from app.runtime import job_service

router = APIRouter(prefix="/jobs", tags=["jobs"])


def to_response(job: Job) -> JobResponse:
    return JobResponse(
        id=job.id,
        kind=job.kind,
        idempotency_key=job.idempotency_key,
        status=job.status,
        progress=job.progress,
        stage=job.stage,
        attempt=job.attempt,
        max_attempts=job.max_attempts,
        failure_reason=job.failure_reason,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )


@router.post("", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_job(
    request: JobCreateRequest,
    x_idempotency_key: str = Header(min_length=1, max_length=255),
) -> JobResponse:
    job = await job_service.submit(
        kind=request.kind,
        idempotency_key=x_idempotency_key,
        payload=request.payload,
        max_attempts=request.max_attempts,
        timeout_seconds=request.timeout_seconds,
    )
    return to_response(job)


@router.get("", response_model=list[JobResponse])
async def list_jobs(limit: int = 100) -> list[JobResponse]:
    return [to_response(job) for job in await job_service.list(limit=min(limit, 100))]


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: UUID) -> JobResponse:
    job = await job_service.get(job_id)
    if job is None:
        raise ResourceNotFoundError(f"job {job_id} was not found")
    return to_response(job)
