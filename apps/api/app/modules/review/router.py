from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.domain.ontology import CandidateKind, CandidateStatus
from app.infrastructure.postgres.session import get_session
from app.modules.review import service
from app.modules.review.schemas import (
    AcceptCandidateRequest,
    CandidateCreate,
    CandidateList,
    CandidateRead,
    MergeCandidateRequest,
    PublishResult,
    RejectCandidateRequest,
)

router = APIRouter()
SessionDependency = Annotated[Session, Depends(get_session)]


@router.post(
    "/candidates",
    response_model=CandidateRead,
    status_code=status.HTTP_201_CREATED,
)
def create_candidate(
    command: CandidateCreate,
    session: SessionDependency,
) -> CandidateRead:
    return CandidateRead.model_validate(service.create_candidate(session, command))


@router.get("/candidates", response_model=CandidateList)
def list_candidates(
    session: SessionDependency,
    candidate_status: Annotated[
        CandidateStatus | None, Query(alias="status")
    ] = None,
    candidate_kind: CandidateKind | None = None,
    source_document_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CandidateList:
    items, total = service.list_candidates(
        session,
        status=candidate_status,
        candidate_kind=candidate_kind,
        source_document_id=source_document_id,
        limit=limit,
        offset=offset,
    )
    return CandidateList(
        items=[CandidateRead.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/candidates/{candidate_id}", response_model=CandidateRead)
def get_candidate(
    candidate_id: UUID,
    session: SessionDependency,
) -> CandidateRead:
    return CandidateRead.model_validate(service.get_candidate(session, candidate_id))


@router.post(
    "/candidates/{candidate_id}/accept",
    response_model=PublishResult,
)
def accept_candidate(
    candidate_id: UUID,
    command: AcceptCandidateRequest,
    session: SessionDependency,
) -> PublishResult:
    return service.accept_candidate(session, candidate_id, command)


@router.post(
    "/candidates/{candidate_id}/merge",
    response_model=PublishResult,
)
def merge_candidate(
    candidate_id: UUID,
    command: MergeCandidateRequest,
    session: SessionDependency,
) -> PublishResult:
    return service.merge_candidate(session, candidate_id, command)


@router.post(
    "/candidates/{candidate_id}/reject",
    response_model=CandidateRead,
)
def reject_candidate(
    candidate_id: UUID,
    command: RejectCandidateRequest,
    session: SessionDependency,
) -> CandidateRead:
    return CandidateRead.model_validate(
        service.reject_candidate(session, candidate_id, command)
    )
