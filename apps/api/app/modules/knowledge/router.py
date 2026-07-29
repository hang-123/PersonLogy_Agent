from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.domain.ontology import ObjectType
from app.infrastructure.postgres.session import get_session
from app.modules.knowledge import service
from app.modules.knowledge.schemas import KnowledgeObjectList, KnowledgeObjectRead

router = APIRouter()
SessionDependency = Annotated[Session, Depends(get_session)]


@router.get("/objects", response_model=KnowledgeObjectList)
def list_objects(
    session: SessionDependency,
    object_type: ObjectType | None = None,
    query: Annotated[str | None, Query(max_length=255)] = None,
    include_archived: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> KnowledgeObjectList:
    items, total = service.list_objects(
        session,
        object_type=object_type,
        query=query,
        include_archived=include_archived,
        limit=limit,
        offset=offset,
    )
    return KnowledgeObjectList(
        items=[KnowledgeObjectRead.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/objects/{object_id}", response_model=KnowledgeObjectRead)
def get_object(
    object_id: UUID,
    session: SessionDependency,
) -> KnowledgeObjectRead:
    return KnowledgeObjectRead.model_validate(service.get_object(session, object_id))
