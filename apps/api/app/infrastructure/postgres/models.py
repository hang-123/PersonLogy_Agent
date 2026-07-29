from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.ontology import (
    AggregateKind,
    BasisKind,
    CandidateKind,
    CandidateStatus,
    ClaimStatus,
    DecisionStatus,
    DecisionType,
    EpistemicType,
    EvidenceDirection,
    EvidenceStatus,
    FreshnessStatus,
    JobStatus,
    JobType,
    ObjectStatus,
    ObjectType,
    ProjectionEventType,
    ProjectionStatus,
    RelationStatus,
    SourceStatus,
    SourceType,
    Visibility,
)
from app.domain.relations import RelationType
from app.infrastructure.database import Base


def enum_type(enum_class: type[StrEnum], name: str) -> sa.Enum:
    return sa.Enum(
        enum_class,
        name=name,
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        values_callable=lambda members: [member.value for member in members],
    )


class UUIDPrimaryKeyMixin:
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )


class KnowledgeObject(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "knowledge_object"
    __table_args__ = (
        sa.CheckConstraint("version >= 1", name="version_positive"),
        sa.UniqueConstraint(
            "object_type", "canonical_name", name="uq_knowledge_object_canonical"
        ),
        sa.Index("ix_knowledge_object_type_status", "object_type", "status"),
        sa.Index(
            "ix_knowledge_object_canonical_name_trgm",
            "canonical_name",
            postgresql_using="gin",
            postgresql_ops={"canonical_name": "gin_trgm_ops"},
        ),
    )

    object_type: Mapped[ObjectType] = mapped_column(
        enum_type(ObjectType, "object_type"), nullable=False
    )
    canonical_name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    status: Mapped[ObjectStatus] = mapped_column(
        enum_type(ObjectStatus, "object_status"), nullable=False
    )
    aliases: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=sa.text("'[]'::jsonb")
    )
    attributes: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=sa.text("'{}'::jsonb")
    )
    visibility: Mapped[Visibility] = mapped_column(
        enum_type(Visibility, "visibility"),
        nullable=False,
        default=Visibility.PRIVATE,
        server_default=Visibility.PRIVATE.value,
    )
    version: Mapped[int] = mapped_column(nullable=False, default=1, server_default="1")
    valid_from: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    captured_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    verified_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    created_by: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    reviewed_by: Mapped[str | None] = mapped_column(sa.String(100))


class KnowledgeRelation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "knowledge_relation"
    __table_args__ = (
        sa.CheckConstraint("version >= 1", name="version_positive"),
        sa.CheckConstraint("source_object_id <> target_object_id", name="different_endpoints"),
        sa.UniqueConstraint(
            "source_object_id",
            "relation_type",
            "target_object_id",
            name="uq_knowledge_relation_semantics",
        ),
        sa.Index("ix_knowledge_relation_source_type", "source_object_id", "relation_type"),
        sa.Index("ix_knowledge_relation_target_type", "target_object_id", "relation_type"),
        sa.Index("ix_knowledge_relation_status", "status"),
    )

    source_object_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("knowledge_object.id", ondelete="RESTRICT"),
        nullable=False,
    )
    relation_type: Mapped[RelationType] = mapped_column(
        enum_type(RelationType, "relation_type"), nullable=False
    )
    target_object_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("knowledge_object.id", ondelete="RESTRICT"),
        nullable=False,
    )
    epistemic_type: Mapped[EpistemicType] = mapped_column(
        enum_type(EpistemicType, "epistemic_type"), nullable=False
    )
    status: Mapped[RelationStatus] = mapped_column(
        enum_type(RelationStatus, "relation_status"),
        nullable=False,
        default=RelationStatus.CANDIDATE,
        server_default=RelationStatus.CANDIDATE.value,
    )
    confidence_note: Mapped[str | None] = mapped_column(sa.Text)
    valid_from: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    captured_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    verified_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    version: Mapped[int] = mapped_column(nullable=False, default=1, server_default="1")
    created_by: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    reviewed_by: Mapped[str | None] = mapped_column(sa.String(100))


class SourceDocument(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "source_document"
    __table_args__ = (
        sa.CheckConstraint("version >= 1", name="version_positive"),
        sa.CheckConstraint("content_size >= 0", name="content_size_nonnegative"),
        sa.UniqueConstraint(
            "content_fingerprint", name="uq_source_document_fingerprint"
        ),
        sa.Index("ix_source_document_status_captured", "status", "captured_at"),
    )

    title: Mapped[str] = mapped_column(sa.String(500), nullable=False)
    source_type: Mapped[SourceType] = mapped_column(
        enum_type(SourceType, "source_type"), nullable=False
    )
    source_url: Mapped[str | None] = mapped_column(sa.Text)
    storage_path: Mapped[str | None] = mapped_column(sa.Text)
    raw_text: Mapped[str | None] = mapped_column(sa.Text)
    content_fingerprint: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    content_size: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    status: Mapped[SourceStatus] = mapped_column(
        enum_type(SourceStatus, "source_status"),
        nullable=False,
        default=SourceStatus.CAPTURED,
        server_default=SourceStatus.CAPTURED.value,
    )
    visibility: Mapped[Visibility] = mapped_column(
        enum_type(Visibility, "source_visibility"),
        nullable=False,
        default=Visibility.PRIVATE,
        server_default=Visibility.PRIVATE.value,
    )
    source_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default=sa.text("'{}'::jsonb"),
    )
    captured_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    version: Mapped[int] = mapped_column(nullable=False, default=1, server_default="1")
    created_by: Mapped[str] = mapped_column(sa.String(100), nullable=False)


class Evidence(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "evidence"
    __table_args__ = (
        sa.Index("ix_evidence_source_document", "source_document_id"),
        sa.Index("ix_evidence_status", "status"),
    )

    source_document_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("source_document.id", ondelete="RESTRICT"),
        nullable=False,
    )
    excerpt: Mapped[str] = mapped_column(sa.Text, nullable=False)
    locator: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=sa.text("'{}'::jsonb")
    )
    content_fingerprint: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    source_level: Mapped[str | None] = mapped_column(sa.String(50))
    status: Mapped[EvidenceStatus] = mapped_column(
        enum_type(EvidenceStatus, "evidence_status"),
        nullable=False,
        default=EvidenceStatus.ACTIVE,
        server_default=EvidenceStatus.ACTIVE.value,
    )
    visibility: Mapped[Visibility] = mapped_column(
        enum_type(Visibility, "evidence_visibility"),
        nullable=False,
        default=Visibility.PRIVATE,
        server_default=Visibility.PRIVATE.value,
    )
    captured_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    created_by: Mapped[str] = mapped_column(sa.String(100), nullable=False)


class EvidenceLink(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "evidence_link"
    __table_args__ = (
        sa.UniqueConstraint(
            "evidence_id",
            "target_kind",
            "target_id",
            "direction",
            name="uq_evidence_link_target_direction",
        ),
        sa.Index("ix_evidence_link_target", "target_kind", "target_id"),
    )

    evidence_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("evidence.id", ondelete="RESTRICT"),
        nullable=False,
    )
    target_kind: Mapped[AggregateKind] = mapped_column(
        enum_type(AggregateKind, "evidence_target_kind"), nullable=False
    )
    target_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    direction: Mapped[EvidenceDirection] = mapped_column(
        enum_type(EvidenceDirection, "evidence_direction"), nullable=False
    )
    note: Mapped[str | None] = mapped_column(sa.Text)
    created_by: Mapped[str] = mapped_column(sa.String(100), nullable=False)


class Claim(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "claim"
    __table_args__ = (
        sa.CheckConstraint("version >= 1", name="version_positive"),
        sa.Index("ix_claim_subject_status", "subject_object_id", "status"),
        sa.Index("ix_claim_freshness", "freshness"),
    )

    subject_object_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("knowledge_object.id", ondelete="RESTRICT"),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(sa.Text, nullable=False)
    epistemic_type: Mapped[EpistemicType] = mapped_column(
        enum_type(EpistemicType, "claim_epistemic_type"), nullable=False
    )
    status: Mapped[ClaimStatus] = mapped_column(
        enum_type(ClaimStatus, "claim_status"),
        nullable=False,
        default=ClaimStatus.DRAFT,
        server_default=ClaimStatus.DRAFT.value,
    )
    freshness: Mapped[FreshnessStatus] = mapped_column(
        enum_type(FreshnessStatus, "claim_freshness"),
        nullable=False,
        default=FreshnessStatus.FRESH,
        server_default=FreshnessStatus.FRESH.value,
    )
    scope: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=sa.text("'{}'::jsonb")
    )
    confidence_note: Mapped[str | None] = mapped_column(sa.Text)
    valid_from: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    confirmed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    version: Mapped[int] = mapped_column(nullable=False, default=1, server_default="1")
    created_by: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    reviewed_by: Mapped[str | None] = mapped_column(sa.String(100))


class ClaimBasis(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "claim_basis"
    __table_args__ = (
        sa.UniqueConstraint(
            "claim_id", "basis_kind", "basis_id", name="uq_claim_basis_reference"
        ),
        sa.Index("ix_claim_basis_reference", "basis_kind", "basis_id"),
    )

    claim_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("claim.id", ondelete="RESTRICT"),
        nullable=False,
    )
    basis_kind: Mapped[BasisKind] = mapped_column(
        enum_type(BasisKind, "claim_basis_kind"), nullable=False
    )
    basis_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    created_by: Mapped[str] = mapped_column(sa.String(100), nullable=False)


class Decision(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "decision"
    __table_args__ = (
        sa.CheckConstraint("version >= 1", name="version_positive"),
        sa.Index("ix_decision_target_status", "target_object_id", "status"),
        sa.Index("ix_decision_review_at", "review_at"),
    )

    target_object_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("knowledge_object.id", ondelete="RESTRICT"),
        nullable=False,
    )
    decision_type: Mapped[DecisionType] = mapped_column(
        enum_type(DecisionType, "decision_type"), nullable=False
    )
    status: Mapped[DecisionStatus] = mapped_column(
        enum_type(DecisionStatus, "decision_status"),
        nullable=False,
        default=DecisionStatus.PROPOSED,
        server_default=DecisionStatus.PROPOSED.value,
    )
    reason: Mapped[str] = mapped_column(sa.Text, nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    review_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    version: Mapped[int] = mapped_column(nullable=False, default=1, server_default="1")
    created_by: Mapped[str] = mapped_column(sa.String(100), nullable=False)


class DecisionBasis(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "decision_basis"
    __table_args__ = (
        sa.UniqueConstraint(
            "decision_id", "basis_kind", "basis_id", name="uq_decision_basis_reference"
        ),
        sa.Index("ix_decision_basis_reference", "basis_kind", "basis_id"),
    )

    decision_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("decision.id", ondelete="RESTRICT"),
        nullable=False,
    )
    basis_kind: Mapped[BasisKind] = mapped_column(
        enum_type(BasisKind, "decision_basis_kind"), nullable=False
    )
    basis_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    created_by: Mapped[str] = mapped_column(sa.String(100), nullable=False)


class Candidate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "candidate"
    __table_args__ = (
        sa.Index("ix_candidate_status_kind", "status", "candidate_kind"),
        sa.Index("ix_candidate_source", "source_document_id"),
    )

    candidate_kind: Mapped[CandidateKind] = mapped_column(
        enum_type(CandidateKind, "candidate_kind"), nullable=False
    )
    status: Mapped[CandidateStatus] = mapped_column(
        enum_type(CandidateStatus, "candidate_status"),
        nullable=False,
        default=CandidateStatus.PENDING_REVIEW,
        server_default=CandidateStatus.PENDING_REVIEW.value,
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    source_document_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("source_document.id", ondelete="RESTRICT"),
    )
    created_by: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    reviewed_by: Mapped[str | None] = mapped_column(sa.String(100))
    reviewed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    rejection_reason: Mapped[str | None] = mapped_column(sa.Text)
    published_target_kind: Mapped[AggregateKind | None] = mapped_column(
        enum_type(AggregateKind, "candidate_published_target_kind")
    )
    published_target_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))


class ObjectVersion(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "object_version"
    __table_args__ = (
        sa.CheckConstraint("version >= 1", name="version_positive"),
        sa.UniqueConstraint(
            "aggregate_kind",
            "aggregate_id",
            "version",
            name="uq_object_version_aggregate_version",
        ),
        sa.Index("ix_object_version_aggregate", "aggregate_kind", "aggregate_id"),
    )

    aggregate_kind: Mapped[AggregateKind] = mapped_column(
        enum_type(AggregateKind, "version_aggregate_kind"), nullable=False
    )
    aggregate_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    version: Mapped[int] = mapped_column(nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    reason: Mapped[str] = mapped_column(sa.Text, nullable=False)
    created_by: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )


class AuditLog(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "audit_log"
    __table_args__ = (
        sa.Index("ix_audit_log_target", "target_kind", "target_id"),
        sa.Index("ix_audit_log_occurred_at", "occurred_at"),
    )

    command: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    actor: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    target_kind: Mapped[AggregateKind] = mapped_column(
        enum_type(AggregateKind, "audit_target_kind"), nullable=False
    )
    target_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    reason: Mapped[str] = mapped_column(sa.Text, nullable=False)
    request_id: Mapped[str | None] = mapped_column(sa.String(100))
    occurred_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )


class ProcessingJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "processing_job"
    __table_args__ = (
        sa.CheckConstraint("attempt_count >= 0", name="attempt_count_nonnegative"),
        sa.CheckConstraint("max_attempts >= 1", name="max_attempts_positive"),
        sa.Index("ix_processing_job_claim", "status", "next_attempt_at", "created_at"),
        sa.Index("ix_processing_job_lease", "status", "lease_expires_at"),
    )

    job_type: Mapped[JobType] = mapped_column(enum_type(JobType, "job_type"), nullable=False)
    status: Mapped[JobStatus] = mapped_column(
        enum_type(JobStatus, "job_status"),
        nullable=False,
        default=JobStatus.PENDING,
        server_default=JobStatus.PENDING.value,
    )
    input_reference: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    result_summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    attempt_count: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    max_attempts: Mapped[int] = mapped_column(nullable=False, default=3, server_default="3")
    error_summary: Mapped[str | None] = mapped_column(sa.Text)
    lease_owner: Mapped[str | None] = mapped_column(sa.String(100))
    lease_expires_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    next_attempt_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))


class GraphProjectionEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "graph_projection_event"
    __table_args__ = (
        sa.CheckConstraint("target_version >= 1", name="target_version_positive"),
        sa.CheckConstraint("attempt_count >= 0", name="attempt_count_nonnegative"),
        sa.UniqueConstraint(
            "aggregate_kind",
            "aggregate_id",
            "event_type",
            "target_version",
            "mapping_version",
            name="uq_graph_projection_event_idempotency",
        ),
        sa.Index("ix_graph_projection_event_pending", "status", "available_at", "created_at"),
    )

    aggregate_kind: Mapped[AggregateKind] = mapped_column(
        enum_type(AggregateKind, "projection_aggregate_kind"), nullable=False
    )
    aggregate_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    event_type: Mapped[ProjectionEventType] = mapped_column(
        enum_type(ProjectionEventType, "projection_event_type"), nullable=False
    )
    target_version: Mapped[int] = mapped_column(nullable=False)
    mapping_version: Mapped[str] = mapped_column(sa.String(50), nullable=False)
    status: Mapped[ProjectionStatus] = mapped_column(
        enum_type(ProjectionStatus, "projection_status"),
        nullable=False,
        default=ProjectionStatus.PENDING,
        server_default=ProjectionStatus.PENDING.value,
    )
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=sa.text("'{}'::jsonb")
    )
    attempt_count: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    error_summary: Mapped[str | None] = mapped_column(sa.Text)
    available_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    processed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))


class GraphProjectionCheckpoint(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "graph_projection_checkpoint"
    __table_args__ = (
        sa.CheckConstraint("projection_version >= 0", name="projection_version_nonnegative"),
        sa.CheckConstraint("object_count >= 0", name="object_count_nonnegative"),
        sa.CheckConstraint("relation_count >= 0", name="relation_count_nonnegative"),
        sa.UniqueConstraint("mapping_version", name="uq_graph_projection_checkpoint_mapping"),
    )

    mapping_version: Mapped[str] = mapped_column(sa.String(50), nullable=False)
    projection_version: Mapped[int] = mapped_column(
        nullable=False, default=0, server_default="0"
    )
    status: Mapped[ProjectionStatus] = mapped_column(
        enum_type(ProjectionStatus, "checkpoint_projection_status"),
        nullable=False,
        default=ProjectionStatus.PENDING,
        server_default=ProjectionStatus.PENDING.value,
    )
    last_event_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    projected_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    last_validated_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    object_count: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    relation_count: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    validation_diff: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=sa.text("'{}'::jsonb")
    )
