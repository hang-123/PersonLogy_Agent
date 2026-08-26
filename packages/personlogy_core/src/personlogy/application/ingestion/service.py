"""Application service for importing normalized conversations."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from personlogy.application.orchestration import JobService
from personlogy.domain.job import Job
from personlogy.domain.source.conversation import Conversation, ConversationMessage
from personlogy.domain.source.models import Project, Source, SourceKind
from personlogy.ports.unit_of_work import UnitOfWorkFactory
from personlogy.shared.errors import DomainValidationError


@dataclass(frozen=True, slots=True)
class IncomingConversationMessage:
    external_id: str
    role: str
    content: str
    ordinal: int
    created_at: datetime | None = None
    parent_external_id: str | None = None
    attachments: tuple[dict[str, object], ...] = ()


@dataclass(frozen=True, slots=True)
class ConversationImportResult:
    project_id: UUID
    source_id: UUID
    conversation_id: UUID
    job: Job
    imported_message_count: int
    duplicate_message_count: int


class ConversationImportService:
    def __init__(self, uow_factory: UnitOfWorkFactory, job_service: JobService) -> None:
        self._uow_factory = uow_factory
        self._job_service = job_service

    async def import_conversation(
        self,
        *,
        project_name: str,
        project_slug: str,
        conversation_external_id: str,
        title: str,
        messages: tuple[IncomingConversationMessage, ...],
        metadata: dict[str, object] | None = None,
    ) -> ConversationImportResult:
        if not messages:
            raise DomainValidationError("conversation must contain at least one message")

        imported_count = 0
        duplicate_count = 0
        async with self._uow_factory() as uow:
            project = await uow.sources.get_project_by_slug(project_slug)
            if project is None:
                project = Project(name=project_name, slug=project_slug)
                await uow.sources.add_project(project)

            conversation = await uow.sources.get_conversation(
                project.id, conversation_external_id
            )
            if conversation is None:
                source = Source(project.id, SourceKind.CONVERSATION, title)
                await uow.sources.add_source(source)
                conversation = Conversation(
                    project_id=project.id,
                    source_id=source.id,
                    external_id=conversation_external_id,
                    title=title,
                    metadata=metadata or {},
                )
                await uow.sources.add_conversation(conversation)

            for message in messages:
                normalized = ConversationMessage(
                    conversation_id=conversation.id,
                    external_id=message.external_id,
                    role=message.role,
                    content=message.content,
                    ordinal=message.ordinal,
                    content_hash=_content_hash(message.content),
                    created_at=_normalize_datetime(message.created_at),
                    parent_external_id=message.parent_external_id,
                    attachments=message.attachments,
                )
                existing = await uow.sources.get_message(
                    conversation.id, normalized.external_id
                )
                if existing is not None:
                    if not _same_message(existing, normalized):
                        raise DomainValidationError(
                            f"message {normalized.external_id} conflicts with existing content"
                        )
                    duplicate_count += 1
                    continue
                await uow.sources.add_message(normalized)
                imported_count += 1
            await uow.commit()

        batch_hash = _batch_hash(messages)
        job = await self._job_service.submit(
            kind="conversation.import",
            idempotency_key=(
                f"conversation-import:{project_slug}:{conversation_external_id}:{batch_hash}"
            ),
            payload={
                "project_id": str(project.id),
                "source_id": str(conversation.source_id),
                "conversation_id": str(conversation.id),
                "imported_message_count": imported_count,
                "duplicate_message_count": duplicate_count,
            },
        )
        return ConversationImportResult(
            project_id=project.id,
            source_id=conversation.source_id,
            conversation_id=conversation.id,
            job=job,
            imported_message_count=imported_count,
            duplicate_message_count=duplicate_count,
        )


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _batch_hash(messages: tuple[IncomingConversationMessage, ...]) -> str:
    canonical = [
        {
            "id": message.external_id,
            "role": message.role,
            "content_hash": _content_hash(message.content),
            "ordinal": message.ordinal,
            "created_at": message.created_at.isoformat() if message.created_at else None,
            "parent": message.parent_external_id,
            "attachments": list(message.attachments),
        }
        for message in messages
    ]
    encoded = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _normalize_datetime(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _same_message(left: ConversationMessage, right: ConversationMessage) -> bool:
    return (
        left.role == right.role
        and left.content_hash == right.content_hash
        and left.ordinal == right.ordinal
        and left.parent_external_id == right.parent_external_id
    )
