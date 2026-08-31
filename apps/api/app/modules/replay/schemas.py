from datetime import datetime
from uuid import UUID

from personlogy.domain.job import JobStatus
from personlogy.domain.replay import ReplayPlanStatus
from pydantic import BaseModel, Field


class ReplayVersionResponse(BaseModel):
    schema_version: str | None
    compiler_version: str
    embedding_version: str | None
    index_version: int | None


class ReplayPlanCreateRequest(BaseModel):
    project_id: UUID
    source_version_id: UUID
    parent_job_id: UUID | None = None
    target_schema_version: str | None = Field(default=None, min_length=1, max_length=100)
    target_compiler_version: str | None = Field(default=None, min_length=1, max_length=200)
    target_embedding_version: str | None = Field(default=None, min_length=1, max_length=200)
    target_index_version: int | None = Field(default=None, ge=1)


class ReplayPlanResponse(BaseModel):
    plan_id: UUID
    project_id: UUID
    source_version_id: UUID
    parent_trace_id: str
    parent_job_id: UUID | None
    baseline_input_content_hash: str
    baseline_versions: ReplayVersionResponse
    target_input_content_hash: str
    target_versions: ReplayVersionResponse
    status: ReplayPlanStatus
    replay_job_id: UUID | None
    created_at: datetime
    approved_at: datetime | None


class ReplayApprovalResponse(BaseModel):
    plan_id: UUID
    job_id: UUID
    trace_id: str
    parent_trace_id: str
    parent_job_id: UUID | None
    status: JobStatus


class ReplayCompareRequest(BaseModel):
    original_output_digest: str | None = Field(default=None, min_length=64, max_length=64)
    replay_output_digest: str | None = Field(default=None, min_length=64, max_length=64)


class ReplayComparisonResponse(BaseModel):
    comparison_id: UUID
    project_id: UUID
    plan_id: UUID
    source_version_id: UUID
    replay_job_id: UUID
    difference_dimensions: list[str]
    output_changed: bool | None
    original_output_digest: str | None
    replay_output_digest: str | None
    status: str
    created_at: datetime


class ReplayPlanDetailResponse(BaseModel):
    plan: ReplayPlanResponse
    comparisons: list[ReplayComparisonResponse]
