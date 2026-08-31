from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class LineageLinkResponse(BaseModel):
    link_id: UUID
    project_id: UUID
    from_type: str
    from_id: str
    relation_type: str
    to_type: str
    to_id: str
    created_at: datetime
    metadata: dict[str, object]


class LineageTraceResponse(BaseModel):
    root_type: str
    root_id: str
    links: list[LineageLinkResponse]
