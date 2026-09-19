from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from personlogy.domain.capture.models import CaptureResultStatus


class CaptureSourceRequest(BaseModel):
    kind: str = Field(min_length=1, max_length=100)
    scope: str = Field(min_length=1, max_length=255)
    session_key: str = Field(min_length=1, max_length=255)
    item_key: str = Field(min_length=1, max_length=255)
    revision: int = Field(default=0, ge=0)


class CaptureEventRequest(BaseModel):
    schema_version: int = Field(default=1, strict=True)
    event_id: UUID
    producer_id: str = Field(min_length=1, max_length=255)
    stream_id: str = Field(min_length=1, max_length=255)
    sequence: int = Field(ge=1)
    source: CaptureSourceRequest
    occurred_at: datetime | None = None
    captured_at: datetime
    rule_version: str = Field(min_length=1, max_length=100)
    payload_hash: str = Field(pattern=r"^[a-fA-F0-9]{64}$")
    payload: dict[str, Any]


class CaptureEventsRequest(BaseModel):
    events: list[CaptureEventRequest] = Field(min_length=1, max_length=100)


class CaptureEventResultResponse(BaseModel):
    event_id: UUID
    status: CaptureResultStatus
    server_receipt_id: str | None = None
    error_code: str | None = None
    error_summary: str | None = None


class CaptureEventsResponse(BaseModel):
    receipt_id: str
    results: list[CaptureEventResultResponse] = Field(min_length=1, max_length=100)
