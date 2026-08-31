from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class SchemaChangeResponse(BaseModel):
    kind: str
    path: str
    before: Any | None = None
    after: Any | None = None


class SchemaProposalResponse(BaseModel):
    id: UUID
    namespace: str
    base_version: int
    target_version: int
    definition: dict[str, object]
    changes: list[SchemaChangeResponse]
    author: str
    status: str
    created_at: datetime
    validated_at: datetime | None
    approved_by: str | None
    approved_at: datetime | None
    applied_at: datetime | None
    rolled_back_at: datetime | None


class SchemaProposalCreateRequest(BaseModel):
    namespace: str = Field(min_length=1, max_length=255)
    target_definition: dict[str, object]
    author: str = Field(min_length=1, max_length=255)


class SchemaApprovalRequest(BaseModel):
    approver: str = Field(min_length=1, max_length=255)
