from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ConversationMessageRequest(BaseModel):
    message_id: str = Field(min_length=1, max_length=255)
    role: str = Field(min_length=1, max_length=50)
    content: str = Field(min_length=1, max_length=1_000_000)
    ordinal: int = Field(ge=0)
    created_at: datetime | None = None
    parent_message_id: str | None = Field(default=None, max_length=255)
    attachments: list[dict[str, Any]] = Field(default_factory=list)


class ConversationImportRequest(BaseModel):
    project_name: str = Field(min_length=1, max_length=255)
    project_slug: str = Field(min_length=1, max_length=100)
    conversation_id: str = Field(min_length=1, max_length=255)
    title: str = Field(min_length=1, max_length=255)
    messages: list[ConversationMessageRequest] = Field(min_length=1, max_length=1000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConversationImportResponse(BaseModel):
    project_id: UUID
    source_id: UUID
    conversation_id: UUID
    job_id: UUID
    imported_message_count: int
    duplicate_message_count: int
