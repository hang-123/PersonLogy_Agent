from datetime import datetime
from typing import Any
from uuid import UUID

from personlogy.domain.job import JobStatus
from pydantic import BaseModel, Field


class JobCreateRequest(BaseModel):
    kind: str = Field(min_length=1, max_length=100)
    payload: dict[str, Any] = Field(default_factory=dict)
    max_attempts: int = Field(default=3, ge=1, le=10)
    timeout_seconds: int = Field(default=900, ge=1, le=86400)


class JobResponse(BaseModel):
    id: UUID
    kind: str
    idempotency_key: str
    status: JobStatus
    progress: int
    stage: str
    attempt: int
    max_attempts: int
    failure_reason: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
