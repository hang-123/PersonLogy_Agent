from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ReviewTaskResponse(BaseModel):
    id: UUID
    run_id: UUID
    candidate_id: UUID
    candidate_kind: str
    status: str
    reviewer_id: str | None
    reason: str | None
    version: int
    before: dict[str, object]
    after: dict[str, object]
    created_at: datetime
    reviewed_at: datetime | None


class ReviewDecisionRequest(BaseModel):
    decision: Literal["approved", "rejected", "revised"]
    reviewer_id: str = Field(min_length=1, max_length=255)
    reason: str = Field(min_length=1, max_length=2000)
    expected_version: int | None = Field(default=None, ge=1)
    changes: dict[str, object] = Field(default_factory=dict)
