from uuid import UUID

from fastapi import APIRouter, Header, status
from personlogy.domain.governance.models import CandidateKind
from personlogy.domain.writeback.models import CandidateRef, WritebackItem, WritebackRecord

from app.application.errors import ResourceNotFoundError
from app.modules.writebacks.schemas import (
    WritebackCreateRequest,
    WritebackItemResponse,
    WritebackResponse,
)
from app.runtime import writeback_service

router = APIRouter(prefix="/writebacks", tags=["writeback"])


def to_response(record: WritebackRecord) -> WritebackResponse:
    return WritebackResponse(
        id=record.id,
        project_id=record.project_id,
        governance_run_id=record.governance_run_id,
        status=record.status.value,
        candidate_count=len(record.candidates),
        effects_job_id=record.effects_job_id,
        okf_object_key=record.okf_object_key,
        index_job_id=record.index_job_id,
        error_code=record.error_code,
        created_at=record.created_at,
        committed_at=record.committed_at,
        completed_at=record.completed_at,
    )


def item_to_response(item: WritebackItem) -> WritebackItemResponse:
    return WritebackItemResponse(
        id=item.id,
        candidate_id=item.candidate_id,
        candidate_kind=item.candidate_kind.value,
        before_status=item.before_status.value,
        after_status=item.after_status.value,
        before_digest=item.before_digest,
        after_digest=item.after_digest,
        result=item.result,
        created_at=item.created_at,
    )


@router.post("", response_model=WritebackResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_writeback(
    request: WritebackCreateRequest,
    x_idempotency_key: str = Header(min_length=1, max_length=255),
) -> WritebackResponse:
    record, _ = await writeback_service.submit(
        project_id=request.project_id,
        governance_run_id=request.governance_run_id,
        candidates=tuple(
            CandidateRef(
                candidate_id=item.candidate_id,
                candidate_kind=CandidateKind(item.candidate_kind),
                expected_review_version=item.expected_review_version,
            )
            for item in request.candidates
        ),
        idempotency_key=x_idempotency_key,
        schema_namespace=request.schema_namespace,
        schema_version=request.schema_version,
    )
    return to_response(record)


@router.get("/{writeback_id}", response_model=WritebackResponse)
async def get_writeback(writeback_id: UUID) -> WritebackResponse:
    record = await writeback_service.get(writeback_id)
    if record is None:
        raise ResourceNotFoundError(f"writeback {writeback_id} was not found")
    return to_response(record)


@router.get("/{writeback_id}/items", response_model=list[WritebackItemResponse])
async def list_writeback_items(writeback_id: UUID) -> list[WritebackItemResponse]:
    record = await writeback_service.get(writeback_id)
    if record is None:
        raise ResourceNotFoundError(f"writeback {writeback_id} was not found")
    return [item_to_response(item) for item in await writeback_service.list_items(writeback_id)]
