from uuid import UUID

from pydantic import BaseModel


class PdfImportResponse(BaseModel):
    project_id: UUID
    source_id: UUID
    source_version_id: UUID
    version: int
    content_hash: str
    object_key: str
    page_count: int
    job_id: UUID
    reused_version: bool
