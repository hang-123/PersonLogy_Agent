from uuid import UUID

from personlogy.domain.job import JobStatus
from pydantic import BaseModel, Field


class EvidenceResponse(BaseModel):
    citation_id: UUID
    quote: str
    source_id: UUID
    source_title: str
    source_version_id: UUID
    locator: dict[str, object]


class RelationPathResponse(BaseModel):
    relation_id: UUID
    relation_type: str
    direction: str
    source_id: UUID
    source_title: str
    target_id: UUID
    target_title: str


class RetrievalHitResponse(BaseModel):
    claim_id: UUID
    project_id: UUID
    statement: str
    subject_id: UUID
    subject_title: str
    score: float
    evidence: list[EvidenceResponse]
    relations: list[RelationPathResponse]


class RetrievalSearchResponse(BaseModel):
    project_id: UUID
    query: str
    hits: list[RetrievalHitResponse]


class RetrievalAnswerRequest(BaseModel):
    project_id: UUID
    question: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=5, ge=1, le=20)
    expand_relations: bool = False


class RetrievalAnswerResponse(BaseModel):
    project_id: UUID
    question: str
    answer: str
    mode: str
    hit_count: int
    hits: list[RetrievalHitResponse]
    citations: list[EvidenceResponse]
    relations: list[RelationPathResponse]
    uncertainty: list[str]


class RetrievalIndexResponse(BaseModel):
    project_id: UUID
    job_id: UUID
    status: JobStatus
    progress: int
    stage: str
