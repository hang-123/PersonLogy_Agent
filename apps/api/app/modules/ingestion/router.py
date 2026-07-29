from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.infrastructure.postgres.session import get_session
from app.modules.ingestion import service
from app.modules.ingestion.schemas import (
    EvidenceCreate,
    EvidenceRead,
    SourceCreate,
    SourceDetail,
    SourceList,
    SourceRead,
)

router = APIRouter()
SessionDependency = Annotated[Session, Depends(get_session)]


@router.get("/sources", response_model=SourceList)
def list_sources(
    session: SessionDependency,
    query: Annotated[str | None, Query(max_length=255)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SourceList:
    items, total = service.list_sources(
        session,
        query=query,
        limit=limit,
        offset=offset,
    )
    return SourceList(
        items=[SourceRead.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/sources", response_model=SourceRead, status_code=status.HTTP_201_CREATED)
def create_source(
    command: SourceCreate,
    session: SessionDependency,
) -> SourceRead:
    return SourceRead.model_validate(service.create_source(session, command))


@router.get("/sources/{source_id}", response_model=SourceDetail)
def get_source(
    source_id: UUID,
    session: SessionDependency,
) -> SourceDetail:
    source = SourceRead.model_validate(service.get_source(session, source_id))
    evidence = [
        EvidenceRead.model_validate(item)
        for item in service.list_source_evidence(session, source_id)
    ]
    return SourceDetail(**source.model_dump(), evidence=evidence)


@router.post(
    "/sources/{source_id}/evidence",
    response_model=EvidenceRead,
    status_code=status.HTTP_201_CREATED,
)
def create_evidence(
    source_id: UUID,
    command: EvidenceCreate,
    session: SessionDependency,
) -> EvidenceRead:
    return EvidenceRead.model_validate(
        service.create_evidence(session, source_id, command)
    )


@router.get("/evidence/{evidence_id}", response_model=EvidenceRead)
def get_evidence(
    evidence_id: UUID,
    session: SessionDependency,
) -> EvidenceRead:
    return EvidenceRead.model_validate(service.get_evidence(session, evidence_id))
