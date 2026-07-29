from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.application.errors import ResourceNotFoundError
from app.domain.ontology import ObjectStatus, ObjectType
from app.infrastructure.postgres.models import KnowledgeObject


def list_objects(
    session: Session,
    *,
    object_type: ObjectType | None,
    query: str | None,
    include_archived: bool,
    limit: int,
    offset: int,
) -> tuple[list[KnowledgeObject], int]:
    filters: list[sa.ColumnElement[bool]] = []
    if object_type is not None:
        filters.append(KnowledgeObject.object_type == object_type)
    if not include_archived:
        filters.append(KnowledgeObject.status != ObjectStatus.ARCHIVED)
    if query and query.strip():
        pattern = f"%{query.strip()}%"
        filters.append(
            sa.or_(
                KnowledgeObject.canonical_name.ilike(pattern),
                KnowledgeObject.display_name.ilike(pattern),
                sa.cast(KnowledgeObject.aliases, sa.Text).ilike(pattern),
            )
        )

    total = session.scalar(
        sa.select(sa.func.count()).select_from(KnowledgeObject).where(*filters)
    )
    items = list(
        session.scalars(
            sa.select(KnowledgeObject)
            .where(*filters)
            .order_by(KnowledgeObject.updated_at.desc(), KnowledgeObject.id)
            .limit(limit)
            .offset(offset)
        )
    )
    return items, int(total or 0)


def get_object(session: Session, object_id: UUID) -> KnowledgeObject:
    knowledge_object = session.get(KnowledgeObject, object_id)
    if knowledge_object is None:
        raise ResourceNotFoundError(f"knowledge object {object_id} was not found")
    return knowledge_object
