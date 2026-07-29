from datetime import UTC, datetime
from hashlib import sha256
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.application.errors import ConflictError, ResourceNotFoundError
from app.domain.ontology import AggregateKind
from app.infrastructure.postgres.models import AuditLog, Evidence, SourceDocument
from app.modules.ingestion.schemas import EvidenceCreate, SourceCreate


def _fingerprint(content: str) -> str:
    normalized = "\n".join(line.rstrip() for line in content.strip().splitlines())
    return sha256(normalized.encode("utf-8")).hexdigest()


def create_source(session: Session, command: SourceCreate) -> SourceDocument:
    fingerprint_input = (
        command.raw_text
        or (str(command.source_url) if command.source_url else None)
        or command.storage_path
    )
    if fingerprint_input is None:
        raise ValueError("source fingerprint input is required")
    fingerprint = _fingerprint(fingerprint_input)

    with session.begin():
        existing_id = session.scalar(
            sa.select(SourceDocument.id).where(
                SourceDocument.content_fingerprint == fingerprint
            )
        )
        if existing_id is not None:
            raise ConflictError(f"duplicate source content; existing source: {existing_id}")

        source = SourceDocument(
            title=command.title.strip(),
            source_type=command.source_type,
            source_url=str(command.source_url) if command.source_url else None,
            storage_path=command.storage_path,
            raw_text=command.raw_text,
            content_fingerprint=fingerprint,
            content_size=len((command.raw_text or "").encode("utf-8")),
            status=command.status,
            visibility=command.visibility,
            source_metadata=command.source_metadata,
            captured_at=command.captured_at or datetime.now(UTC),
            created_by=command.created_by,
        )
        session.add(source)
        session.flush()
        session.add(
            AuditLog(
                command="source.create",
                actor=command.created_by,
                target_kind=AggregateKind.SOURCE_DOCUMENT,
                target_id=source.id,
                before=None,
                after={
                    "id": str(source.id),
                    "title": source.title,
                    "source_type": source.source_type.value,
                    "content_fingerprint": source.content_fingerprint,
                    "status": source.status.value,
                    "version": source.version,
                },
                reason="source material created",
            )
        )
    return source



def list_sources(
    session: Session,
    *,
    query: str | None,
    limit: int,
    offset: int,
) -> tuple[list[SourceDocument], int]:
    filters: list[sa.ColumnElement[bool]] = []
    if query and query.strip():
        pattern = f"%{query.strip()}%"
        filters.append(
            sa.or_(
                SourceDocument.title.ilike(pattern),
                SourceDocument.source_url.ilike(pattern),
                SourceDocument.raw_text.ilike(pattern),
            )
        )
    total = session.scalar(
        sa.select(sa.func.count()).select_from(SourceDocument).where(*filters)
    )
    items = list(
        session.scalars(
            sa.select(SourceDocument)
            .where(*filters)
            .order_by(SourceDocument.captured_at.desc(), SourceDocument.id)
            .limit(limit)
            .offset(offset)
        )
    )
    return items, int(total or 0)

def get_source(session: Session, source_id: UUID) -> SourceDocument:
    source = session.get(SourceDocument, source_id)
    if source is None:
        raise ResourceNotFoundError(f"source document {source_id} was not found")
    return source


def list_source_evidence(session: Session, source_id: UUID) -> list[Evidence]:
    get_source(session, source_id)
    return list(
        session.scalars(
            sa.select(Evidence)
            .where(Evidence.source_document_id == source_id)
            .order_by(Evidence.created_at, Evidence.id)
        )
    )


def create_evidence(
    session: Session,
    source_id: UUID,
    command: EvidenceCreate,
) -> Evidence:
    with session.begin():
        source = session.get(SourceDocument, source_id)
        if source is None:
            raise ResourceNotFoundError(f"source document {source_id} was not found")

        evidence = Evidence(
            source_document_id=source.id,
            excerpt=command.excerpt.strip(),
            locator=command.locator,
            content_fingerprint=_fingerprint(command.excerpt),
            source_level=command.source_level,
            status=command.status,
            visibility=command.visibility,
            captured_at=command.captured_at or datetime.now(UTC),
            created_by=command.created_by,
        )
        session.add(evidence)
        session.flush()
        session.add(
            AuditLog(
                command="evidence.create",
                actor=command.created_by,
                target_kind=AggregateKind.EVIDENCE,
                target_id=evidence.id,
                before=None,
                after={
                    "id": str(evidence.id),
                    "source_document_id": str(source.id),
                    "content_fingerprint": evidence.content_fingerprint,
                    "locator": evidence.locator,
                    "status": evidence.status.value,
                },
                reason="evidence excerpt created",
            )
        )
    return evidence


def get_evidence(session: Session, evidence_id: UUID) -> Evidence:
    evidence = session.get(Evidence, evidence_id)
    if evidence is None:
        raise ResourceNotFoundError(f"evidence {evidence_id} was not found")
    return evidence
