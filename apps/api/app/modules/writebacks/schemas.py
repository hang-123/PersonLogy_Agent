from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class WritebackCandidateRequest(BaseModel):
    candidate_id: UUID
    candidate_kind: Literal["node", "claim", "relation"]
    expected_review_version: int | None = Field(default=None, ge=1)


class WritebackCreateRequest(BaseModel):
    project_id: UUID
    governance_run_id: UUID
    candidates: list[WritebackCandidateRequest] = Field(min_length=1, max_length=500)
    schema_namespace: str = Field(default="personlogy", min_length=1, max_length=255)
    schema_version: int = Field(default=1, ge=1)


class WritebackResponse(BaseModel):
    id: UUID
    project_id: UUID
    governance_run_id: UUID
    status: str
    candidate_count: int
    effects_job_id: UUID | None
    okf_object_key: str | None
    index_job_id: UUID | None
    error_code: str | None
    created_at: datetime
    committed_at: datetime | None
    completed_at: datetime | None


class WritebackItemResponse(BaseModel):
    id: UUID
    candidate_id: UUID
    candidate_kind: str
    before_status: str
    after_status: str
    before_digest: str
    after_digest: str
    result: str
    created_at: datetime
