from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.application.errors import (
    ConflictError,
    InvalidCandidateError,
    ResourceNotFoundError,
)
from app.domain.ontology import (
    AggregateKind,
    CandidateKind,
    CandidateStatus,
    DomainValidationError,
    EvidenceDirection,
    EvidenceStatus,
    ObjectStatus,
    ProjectionEventType,
    ProjectionStatus,
    RelationStatus,
    validate_object_status,
)
from app.domain.relations import validate_relation
from app.infrastructure.postgres.models import (
    AuditLog,
    Candidate,
    Evidence,
    EvidenceLink,
    GraphProjectionEvent,
    KnowledgeObject,
    KnowledgeRelation,
    ObjectVersion,
    SourceDocument,
)
from app.modules.review.schemas import (
    AcceptCandidateRequest,
    CandidateCreate,
    MergeCandidateRequest,
    ObjectPublishPayload,
    PublishResult,
    RejectCandidateRequest,
    RelationPublishPayload,
)

MAPPING_VERSION = "v1"


def create_candidate(session: Session, command: CandidateCreate) -> Candidate:
    with session.begin():
        if (
            command.source_document_id is not None
            and session.get(SourceDocument, command.source_document_id) is None
        ):
            raise ResourceNotFoundError(
                f"source document {command.source_document_id} was not found"
            )

        candidate = Candidate(
            candidate_kind=command.candidate_kind,
            payload=command.payload,
            source_document_id=command.source_document_id,
            created_by=command.created_by,
        )
        session.add(candidate)
        session.flush()
        session.add(
            AuditLog(
                command="candidate.create",
                actor=command.created_by,
                target_kind=AggregateKind.CANDIDATE,
                target_id=candidate.id,
                before=None,
                after=_candidate_audit_snapshot(candidate),
                reason="candidate submitted for review",
            )
        )
    return candidate


def get_candidate(session: Session, candidate_id: UUID) -> Candidate:
    candidate = session.get(Candidate, candidate_id)
    if candidate is None:
        raise ResourceNotFoundError(f"candidate {candidate_id} was not found")
    return candidate


def list_candidates(
    session: Session,
    *,
    status: CandidateStatus | None,
    candidate_kind: CandidateKind | None,
    source_document_id: UUID | None,
    limit: int,
    offset: int,
) -> tuple[list[Candidate], int]:
    filters: list[sa.ColumnElement[bool]] = []
    if status is not None:
        filters.append(Candidate.status == status)
    if candidate_kind is not None:
        filters.append(Candidate.candidate_kind == candidate_kind)
    if source_document_id is not None:
        filters.append(Candidate.source_document_id == source_document_id)

    total = session.scalar(
        sa.select(sa.func.count()).select_from(Candidate).where(*filters)
    )
    items = list(
        session.scalars(
            sa.select(Candidate)
            .where(*filters)
            .order_by(Candidate.created_at.desc(), Candidate.id)
            .limit(limit)
            .offset(offset)
        )
    )
    return items, int(total or 0)


def accept_candidate(
    session: Session,
    candidate_id: UUID,
    command: AcceptCandidateRequest,
) -> PublishResult:
    try:
        with session.begin():
            candidate = _locked_pending_candidate(session, candidate_id)
            payload = {**candidate.payload, **command.changes}
            if candidate.candidate_kind is CandidateKind.OBJECT:
                result = _publish_object(session, candidate, payload, command)
            elif candidate.candidate_kind is CandidateKind.RELATION:
                result = _publish_relation(session, candidate, payload, command)
            else:
                raise InvalidCandidateError(
                    f"publishing {candidate.candidate_kind.value} candidates "
                    "is not implemented in this increment"
                )
            return result
    except IntegrityError as error:
        raise ConflictError(
            "publish conflicted with an existing canonical object or relation"
        ) from error



def merge_candidate(
    session: Session,
    candidate_id: UUID,
    command: MergeCandidateRequest,
) -> PublishResult:
    with session.begin():
        candidate = _locked_pending_candidate(session, candidate_id)
        if candidate.candidate_kind is not CandidateKind.OBJECT:
            raise InvalidCandidateError("only object candidates can merge into an object")

        payload = _parse_payload(ObjectPublishPayload, candidate.payload)
        target = session.scalar(
            sa.select(KnowledgeObject)
            .where(KnowledgeObject.id == command.target_object_id)
            .with_for_update()
        )
        if target is None:
            raise ResourceNotFoundError(
                f"knowledge object {command.target_object_id} was not found"
            )
        if target.object_type is not payload.object_type:
            raise DomainValidationError(
                f"candidate type {payload.object_type.value} cannot merge into "
                f"{target.object_type.value}"
            )
        if target.status is ObjectStatus.ARCHIVED:
            raise DomainValidationError("cannot merge into an archived object")

        before = _object_snapshot(target)
        alias_candidates = [
            payload.canonical_name,
            payload.display_name,
            *payload.aliases,
            *command.aliases,
        ]
        reserved = {
            target.canonical_name.casefold(),
            target.display_name.casefold(),
            *(alias.casefold() for alias in target.aliases),
        }
        added_aliases: list[str] = []
        for value in alias_candidates:
            alias = value.strip()
            normalized = alias.casefold()
            if alias and normalized not in reserved:
                reserved.add(normalized)
                added_aliases.append(alias)

        target.aliases = [*target.aliases, *added_aliases]
        target.version += 1
        target.reviewed_by = command.reviewed_by
        candidate.status = CandidateStatus.MERGED
        candidate.reviewed_by = command.reviewed_by
        candidate.reviewed_at = datetime.now(UTC)
        candidate.published_target_kind = AggregateKind.OBJECT
        candidate.published_target_id = target.id
        session.flush()

        after = _object_snapshot(target)
        session.add_all(
            [
                ObjectVersion(
                    aggregate_kind=AggregateKind.OBJECT,
                    aggregate_id=target.id,
                    version=target.version,
                    snapshot=after,
                    reason=command.reason,
                    created_by=command.reviewed_by,
                ),
                AuditLog(
                    command="candidate.merge_object",
                    actor=command.reviewed_by,
                    target_kind=AggregateKind.OBJECT,
                    target_id=target.id,
                    before=before,
                    after=after,
                    reason=command.reason,
                ),
                GraphProjectionEvent(
                    aggregate_kind=AggregateKind.OBJECT,
                    aggregate_id=target.id,
                    event_type=ProjectionEventType.REVISE,
                    target_version=target.version,
                    mapping_version=MAPPING_VERSION,
                    status=ProjectionStatus.PENDING,
                    payload={
                        "candidate_id": str(candidate.id),
                        "target_id": str(target.id),
                        "added_aliases": added_aliases,
                    },
                ),
            ]
        )
        return PublishResult(
            candidate_id=candidate.id,
            candidate_status=CandidateStatus.MERGED,
            target_kind=AggregateKind.OBJECT,
            target_id=target.id,
            target_version=target.version,
        )

def reject_candidate(
    session: Session,
    candidate_id: UUID,
    command: RejectCandidateRequest,
) -> Candidate:
    with session.begin():
        candidate = _locked_pending_candidate(session, candidate_id)
        before = _candidate_audit_snapshot(candidate)
        candidate.status = CandidateStatus.REJECTED
        candidate.reviewed_by = command.reviewed_by
        candidate.reviewed_at = datetime.now(UTC)
        candidate.rejection_reason = command.reason
        session.add(
            AuditLog(
                command="candidate.reject",
                actor=command.reviewed_by,
                target_kind=AggregateKind.CANDIDATE,
                target_id=candidate.id,
                before=before,
                after=_candidate_audit_snapshot(candidate),
                reason=command.reason,
            )
        )
    return candidate


def _locked_pending_candidate(session: Session, candidate_id: UUID) -> Candidate:
    candidate = session.scalar(
        sa.select(Candidate).where(Candidate.id == candidate_id).with_for_update()
    )
    if candidate is None:
        raise ResourceNotFoundError(f"candidate {candidate_id} was not found")
    if candidate.status is not CandidateStatus.PENDING_REVIEW:
        raise ConflictError(
            f"candidate {candidate_id} is already {candidate.status.value}"
        )
    return candidate


def _publish_object(
    session: Session,
    candidate: Candidate,
    raw_payload: dict[str, Any],
    command: AcceptCandidateRequest,
) -> PublishResult:
    payload = _parse_payload(ObjectPublishPayload, raw_payload)
    validate_object_status(payload.object_type, payload.status)

    canonical_name = payload.canonical_name.strip()
    existing_id = session.scalar(
        sa.select(KnowledgeObject.id).where(
            KnowledgeObject.object_type == payload.object_type,
            KnowledgeObject.canonical_name == canonical_name,
        )
    )
    if existing_id is not None:
        raise ConflictError(
            f"canonical object already exists; use merge target {existing_id}"
        )

    knowledge_object = KnowledgeObject(
        object_type=payload.object_type,
        canonical_name=canonical_name,
        display_name=payload.display_name.strip(),
        status=payload.status,
        aliases=payload.aliases,
        attributes=payload.attributes,
        visibility=payload.visibility,
        valid_from=payload.valid_from,
        valid_to=payload.valid_to,
        captured_at=payload.captured_at,
        verified_at=payload.verified_at,
        created_by=command.reviewed_by,
        reviewed_by=command.reviewed_by,
    )
    session.add(knowledge_object)
    session.flush()
    snapshot = _object_snapshot(knowledge_object)
    _record_publish_side_effects(
        session,
        candidate=candidate,
        target_kind=AggregateKind.OBJECT,
        target_id=knowledge_object.id,
        version=knowledge_object.version,
        snapshot=snapshot,
        actor=command.reviewed_by,
        reason=command.reason,
    )
    return PublishResult(
        candidate_id=candidate.id,
        candidate_status=CandidateStatus.ACCEPTED,
        target_kind=AggregateKind.OBJECT,
        target_id=knowledge_object.id,
        target_version=knowledge_object.version,
    )


def _publish_relation(
    session: Session,
    candidate: Candidate,
    raw_payload: dict[str, Any],
    command: AcceptCandidateRequest,
) -> PublishResult:
    payload = _parse_payload(RelationPublishPayload, raw_payload)
    if payload.status is not RelationStatus.CONFIRMED:
        raise DomainValidationError("published relations must use confirmed status")

    source = session.get(KnowledgeObject, payload.source_object_id)
    target = session.get(KnowledgeObject, payload.target_object_id)
    if source is None:
        raise ResourceNotFoundError(
            f"source object {payload.source_object_id} was not found"
        )
    if target is None:
        raise ResourceNotFoundError(
            f"target object {payload.target_object_id} was not found"
        )
    if source.status is ObjectStatus.ARCHIVED or target.status is ObjectStatus.ARCHIVED:
        raise DomainValidationError("archived objects cannot be relation endpoints")

    evidence = list(
        session.scalars(
            sa.select(Evidence).where(Evidence.id.in_(set(payload.evidence_ids)))
        )
    )
    if len(evidence) != len(set(payload.evidence_ids)):
        raise ResourceNotFoundError("one or more evidence items were not found")
    if any(item.status is not EvidenceStatus.ACTIVE for item in evidence):
        raise DomainValidationError("only active evidence can support publication")

    validate_relation(
        payload.relation_type,
        source.object_type,
        target.object_type,
        evidence_count=len(evidence),
    )
    existing_id = session.scalar(
        sa.select(KnowledgeRelation.id).where(
            KnowledgeRelation.source_object_id == source.id,
            KnowledgeRelation.relation_type == payload.relation_type,
            KnowledgeRelation.target_object_id == target.id,
        )
    )
    if existing_id is not None:
        raise ConflictError(f"relation already exists: {existing_id}")

    relation = KnowledgeRelation(
        source_object_id=source.id,
        relation_type=payload.relation_type,
        target_object_id=target.id,
        epistemic_type=payload.epistemic_type,
        status=payload.status,
        confidence_note=payload.confidence_note,
        valid_from=payload.valid_from,
        valid_to=payload.valid_to,
        captured_at=payload.captured_at,
        verified_at=payload.verified_at,
        created_by=command.reviewed_by,
        reviewed_by=command.reviewed_by,
    )
    session.add(relation)
    session.flush()
    for item in evidence:
        session.add(
            EvidenceLink(
                evidence_id=item.id,
                target_kind=AggregateKind.RELATION,
                target_id=relation.id,
                direction=EvidenceDirection.SUPPORTS,
                created_by=command.reviewed_by,
            )
        )

    snapshot = _relation_snapshot(relation, [item.id for item in evidence])
    _record_publish_side_effects(
        session,
        candidate=candidate,
        target_kind=AggregateKind.RELATION,
        target_id=relation.id,
        version=relation.version,
        snapshot=snapshot,
        actor=command.reviewed_by,
        reason=command.reason,
    )
    return PublishResult(
        candidate_id=candidate.id,
        candidate_status=CandidateStatus.ACCEPTED,
        target_kind=AggregateKind.RELATION,
        target_id=relation.id,
        target_version=relation.version,
    )


def _record_publish_side_effects(
    session: Session,
    *,
    candidate: Candidate,
    target_kind: AggregateKind,
    target_id: UUID,
    version: int,
    snapshot: dict[str, Any],
    actor: str,
    reason: str,
) -> None:
    candidate.status = CandidateStatus.ACCEPTED
    candidate.reviewed_by = actor
    candidate.reviewed_at = datetime.now(UTC)
    candidate.published_target_kind = target_kind
    candidate.published_target_id = target_id
    session.add_all(
        [
            ObjectVersion(
                aggregate_kind=target_kind,
                aggregate_id=target_id,
                version=version,
                snapshot=snapshot,
                reason=reason,
                created_by=actor,
            ),
            AuditLog(
                command=f"candidate.publish_{target_kind.value}",
                actor=actor,
                target_kind=target_kind,
                target_id=target_id,
                before=None,
                after=snapshot,
                reason=reason,
            ),
            GraphProjectionEvent(
                aggregate_kind=target_kind,
                aggregate_id=target_id,
                event_type=ProjectionEventType.PUBLISH,
                target_version=version,
                mapping_version=MAPPING_VERSION,
                status=ProjectionStatus.PENDING,
                payload={
                    "candidate_id": str(candidate.id),
                    "target_id": str(target_id),
                },
            ),
        ]
    )


def _parse_payload[PublishPayload: (ObjectPublishPayload, RelationPublishPayload)](
    schema: type[PublishPayload],
    payload: dict[str, Any],
) -> PublishPayload:
    try:
        return schema.model_validate(payload)
    except ValidationError as error:
        details = "; ".join(
            f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}"
            for item in error.errors(include_input=False)
        )
        raise InvalidCandidateError(f"candidate payload is invalid: {details}") from error



def _candidate_audit_snapshot(candidate: Candidate) -> dict[str, Any]:
    return {
        "id": str(candidate.id),
        "candidate_kind": candidate.candidate_kind.value,
        "status": candidate.status.value,
        "source_document_id": (
            str(candidate.source_document_id) if candidate.source_document_id else None
        ),
        "reviewed_by": candidate.reviewed_by,
        "reviewed_at": (
            candidate.reviewed_at.isoformat() if candidate.reviewed_at else None
        ),
        "rejection_reason": candidate.rejection_reason,
        "published_target_kind": (
            candidate.published_target_kind.value
            if candidate.published_target_kind
            else None
        ),
        "published_target_id": (
            str(candidate.published_target_id)
            if candidate.published_target_id
            else None
        ),
    }


def _object_snapshot(knowledge_object: KnowledgeObject) -> dict[str, Any]:
    return {
        "id": str(knowledge_object.id),
        "object_type": knowledge_object.object_type.value,
        "canonical_name": knowledge_object.canonical_name,
        "display_name": knowledge_object.display_name,
        "status": knowledge_object.status.value,
        "aliases": knowledge_object.aliases,
        "attributes": knowledge_object.attributes,
        "visibility": knowledge_object.visibility.value,
        "version": knowledge_object.version,
    }


def _relation_snapshot(
    relation: KnowledgeRelation,
    evidence_ids: list[UUID],
) -> dict[str, Any]:
    return {
        "id": str(relation.id),
        "source_object_id": str(relation.source_object_id),
        "relation_type": relation.relation_type.value,
        "target_object_id": str(relation.target_object_id),
        "epistemic_type": relation.epistemic_type.value,
        "status": relation.status.value,
        "evidence_ids": [str(item) for item in evidence_ids],
        "version": relation.version,
    }
