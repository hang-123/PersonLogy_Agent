from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ContentBlockResponse(BaseModel):
    id: UUID
    source_version_id: UUID
    ordinal: int
    content: str
    content_hash: str
    locator: dict[str, object]


class SourceVersionResponse(BaseModel):
    id: UUID
    source_id: UUID
    version: int
    content_hash: str
    created_at: datetime
    content_available: bool
    blocks: list[ContentBlockResponse]


class SourceVersionSummaryResponse(BaseModel):
    id: UUID
    source_id: UUID
    version: int
    content_hash: str
    created_at: datetime
    content_available: bool


class EvidenceDetailResponse(BaseModel):
    id: UUID
    quote: str
    locator: dict[str, object]
    metadata: dict[str, object]
    content_block: ContentBlockResponse
    source_version: SourceVersionSummaryResponse
