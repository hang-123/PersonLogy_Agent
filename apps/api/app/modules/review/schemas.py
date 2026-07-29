from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.ontology import (
    AggregateKind,
    CandidateKind,
    CandidateStatus,
    EpistemicType,
    ObjectStatus,
    ObjectType,
    RelationStatus,
    Visibility,
)
from app.domain.relations import RelationType


class CandidateCreate(BaseModel):
    candidate_kind: CandidateKind
    payload: dict[str, Any]
    source_document_id: UUID | None = None
    created_by: str = Field(min_length=1, max_length=100)


class CandidateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    candidate_kind: CandidateKind
    status: CandidateStatus
    payload: dict[str, Any]
    source_document_id: UUID | None
    created_by: str
    reviewed_by: str | None
    reviewed_at: datetime | None
    rejection_reason: str | None
    published_target_kind: AggregateKind | None
    published_target_id: UUID | None
    created_at: datetime
    updated_at: datetime


class CandidateList(BaseModel):
    items: list[CandidateRead]
    total: int
    limit: int
    offset: int


class AcceptCandidateRequest(BaseModel):
    reviewed_by: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=1)
    changes: dict[str, Any] = Field(default_factory=dict)


class MergeCandidateRequest(BaseModel):
    target_object_id: UUID
    reviewed_by: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=1)
    aliases: list[str] = Field(default_factory=list)


class RejectCandidateRequest(BaseModel):
    reviewed_by: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=1)


class ObjectPublishPayload(BaseModel):
    object_type: ObjectType
    canonical_name: str = Field(min_length=1, max_length=255)
    display_name: str = Field(min_length=1, max_length=255)
    status: ObjectStatus
    aliases: list[str] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(default_factory=dict)
    visibility: Visibility = Visibility.PRIVATE
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    captured_at: datetime | None = None
    verified_at: datetime | None = None


class RelationPublishPayload(BaseModel):
    source_object_id: UUID
    relation_type: RelationType
    target_object_id: UUID
    epistemic_type: EpistemicType
    status: RelationStatus = RelationStatus.CONFIRMED
    evidence_ids: list[UUID] = Field(default_factory=list)
    confidence_note: str | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    captured_at: datetime | None = None
    verified_at: datetime | None = None


class PublishResult(BaseModel):
    candidate_id: UUID
    candidate_status: CandidateStatus
    target_kind: AggregateKind
    target_id: UUID
    target_version: int
