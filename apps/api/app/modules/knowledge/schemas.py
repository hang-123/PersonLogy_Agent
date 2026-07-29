from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.domain.ontology import ObjectStatus, ObjectType, Visibility


class KnowledgeObjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    object_type: ObjectType
    canonical_name: str
    display_name: str
    status: ObjectStatus
    aliases: list[str]
    attributes: dict[str, Any]
    visibility: Visibility
    version: int
    created_by: str
    reviewed_by: str | None
    created_at: datetime
    updated_at: datetime


class KnowledgeObjectList(BaseModel):
    items: list[KnowledgeObjectRead]
    total: int
    limit: int
    offset: int
