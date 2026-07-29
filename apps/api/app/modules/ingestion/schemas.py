from datetime import datetime
from typing import Any, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from app.domain.ontology import (
    EvidenceStatus,
    SourceStatus,
    SourceType,
    Visibility,
)


class SourceCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    source_type: SourceType
    source_url: HttpUrl | None = None
    storage_path: str | None = None
    raw_text: str | None = None
    status: SourceStatus = SourceStatus.CAPTURED
    visibility: Visibility = Visibility.PRIVATE
    source_metadata: dict[str, Any] = Field(default_factory=dict)
    captured_at: datetime | None = None
    created_by: str = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_content_location(self) -> Self:
        if not any(
            (
                self.raw_text and self.raw_text.strip(),
                self.source_url,
                self.storage_path and self.storage_path.strip(),
            )
        ):
            raise ValueError("raw_text, source_url, or storage_path is required")
        return self


class SourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    source_type: SourceType
    source_url: str | None
    storage_path: str | None
    raw_text: str | None
    content_fingerprint: str
    content_size: int
    status: SourceStatus
    visibility: Visibility
    source_metadata: dict[str, Any]
    captured_at: datetime
    version: int
    created_by: str
    created_at: datetime
    updated_at: datetime


class SourceList(BaseModel):
    items: list[SourceRead]
    total: int
    limit: int
    offset: int


class EvidenceCreate(BaseModel):
    excerpt: str = Field(min_length=1)
    locator: dict[str, Any]
    source_level: str | None = Field(default=None, max_length=50)
    status: EvidenceStatus = EvidenceStatus.ACTIVE
    visibility: Visibility = Visibility.PRIVATE
    captured_at: datetime | None = None
    created_by: str = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_locator(self) -> Self:
        if not self.locator:
            raise ValueError("locator must identify a page, paragraph, anchor, or range")
        return self


class EvidenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_document_id: UUID
    excerpt: str
    locator: dict[str, Any]
    content_fingerprint: str
    source_level: str | None
    status: EvidenceStatus
    visibility: Visibility
    captured_at: datetime
    created_by: str
    created_at: datetime
    updated_at: datetime


class SourceDetail(SourceRead):
    evidence: list[EvidenceRead] = Field(default_factory=list)
