"""Gel persistence adapters for the PersonLogy structured store.

Implements the same Repository / Unit of Work / Queue ports as the SQLite
adapter, backed by a Gel 7 database. See ``GEL/dbschema`` for the authoritative
schema and ``GEL/dbschema/migrations`` for applied migrations.

Runtime contract:
- The target Gel database must have ``allow_user_specified_id := true``
  configured, because the domain generates object UUIDs in Python (they are
  referenced by object keys, job payloads, etc.).
- JSON-valued properties are passed to EdgeQL as JSON text and parsed back with
  :func:`json.loads`; the driver returns ``json`` columns as ``str``.
- Enum properties accept their member name as ``str``.
- Optional properties are written through ``<optional T>`` parameter casts so
  ``None`` is encoded as NULL.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from time import monotonic
from types import TracebackType
from typing import Any, Self, cast
from uuid import UUID

import gel
from gel import errors as gel_errors

from personlogy.domain.governance.models import (
    CandidateKind,
    ConflictRecord,
    DuplicateGroup,
    GovernanceIssue,
    GovernanceRun,
    ReviewTask,
    ReviewTaskStatus,
)
from personlogy.domain.job import Job, JobStatus
from personlogy.domain.knowledge.models import (
    Citation,
    Claim,
    KnowledgeNode,
    VerificationStatus,
)
from personlogy.domain.relation.models import Relation, RelationType
from personlogy.domain.source.conversation import Conversation, ConversationMessage
from personlogy.domain.source.models import (
    ContentBlock,
    Project,
    Source,
    SourceKind,
    SourceVersion,
)
from personlogy.domain.writeback.models import (
    CandidateRef,
    WritebackItem,
    WritebackRecord,
    WritebackStatus,
)
from personlogy.ports.queue import JobQueue
from personlogy.ports.repositories import (
    GovernanceRepository,
    JobRepository,
    KnowledgeRepository,
    SourceRepository,
)
from personlogy.ports.writeback import WritebackRepository
from personlogy.shared.errors import DomainValidationError

__all__ = [
    "GelGovernanceRepository",
    "GelJobQueue",
    "GelKnowledgeRepository",
    "GelSourceRepository",
    "GelStore",
    "GelUnitOfWork",
    "GelUnitOfWorkFactory",
    "GelWritebackRepository",
]


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def _mapping(value: str) -> dict[str, object]:
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise TypeError("stored JSON value is not an object")
    return parsed


def _mappings(value: str) -> tuple[dict[str, object], ...]:
    parsed = json.loads(value)
    if not isinstance(parsed, list):
        raise TypeError("stored JSON value is not a list")
    return tuple(item for item in parsed if isinstance(item, dict))


def _candidate_refs(value: str) -> tuple[CandidateRef, ...]:
    return tuple(
        CandidateRef(
            candidate_id=UUID(str(item["candidate_id"])),
            candidate_kind=CandidateKind(str(item["candidate_kind"])),
            expected_review_version=_optional_int(item.get("expected_review_version")),
        )
        for item in _mappings(value)
    )


def _optional_int(value: object) -> int | None:
    return int(str(value)) if value is not None else None


def _now() -> datetime:
    return datetime.now(UTC)


class _Rollback(Exception):
    """Internal marker used to force a transaction rollback on clean exit."""


class GelStore:
    """Database handle shared by UoW and queue instances."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._client = cast(gel.AsyncIOClient, gel.create_async_client(dsn=dsn))

    @property
    def client(self) -> gel.AsyncIOClient:
        return self._client

    async def aclose(self) -> None:
        await cast(Any, self._client).aclose()

    async def ping(self) -> bool:
        try:
            return bool(await self._client.query_single("select 1"))
        except gel_errors.EdgeDBError:
            return False


def _constraint_error(error: gel_errors.EdgeDBError, message: str) -> DomainValidationError:
    if isinstance(error, (gel_errors.ConstraintViolationError, gel_errors.MissingRequiredError)):
        return DomainValidationError(message)
    raise error


class GelSourceRepository:
    def __init__(self, tx: Any) -> None:
        self._tx = tx

    async def add_project(self, project: Project) -> None:
        try:
            await self._tx.execute(
                """
                insert Project {
                  id := <uuid>$id,
                  name := <str>$name,
                  slug := <str>$slug,
                  created_at := <datetime>$created_at,
                }
                """,
                id=project.id,
                name=project.name,
                slug=project.slug,
                created_at=project.created_at,
            )
        except gel_errors.EdgeDBError as error:
            raise _constraint_error(error, "project slug already exists") from error

    async def get_project_by_slug(self, slug: str) -> Project | None:
        row = await self._tx.query_single(
            """
            select Project { name, slug, created_at }
            filter .slug = <str>$slug
            limit 1
            """,
            slug=slug,
        )
        if row is None:
            return None
        return Project(name=row.name, slug=row.slug, id=row.id, created_at=row.created_at)

    async def add_source(self, source: Source) -> None:
        try:
            await self._tx.execute(
                """
                insert Source {
                  id := <uuid>$id,
                  project := (select Project filter .id = <uuid>$project_id),
                  kind := <default::SourceKind>$kind,
                  title := <str>$title,
                  created_at := <datetime>$created_at,
                }
                """,
                id=source.id,
                project_id=source.project_id,
                kind=source.kind.value,
                title=source.title,
                created_at=source.created_at,
            )
        except gel_errors.EdgeDBError as error:
            raise _constraint_error(error, "source project does not exist") from error

    async def get_source(
        self, project_id: UUID, kind: SourceKind, title: str
    ) -> Source | None:
        row = await self._tx.query_single(
            """
            select Source { id, kind, title, created_at, project: { id } }
            filter .project.id = <uuid>$project_id
               and .kind = <default::SourceKind>$kind
               and .title = <str>$title
            order by .created_at asc
            limit 1
            """,
            project_id=project_id,
            kind=kind.value,
            title=title,
        )
        if row is None:
            return None
        return Source(
            project_id=row.project.id,
            kind=SourceKind(row.kind),
            title=row.title,
            id=row.id,
            created_at=row.created_at,
        )

    async def add_conversation(self, conversation: Conversation) -> None:
        try:
            await self._tx.execute(
                """
                insert Conversation {
                  id := <uuid>$id,
                  project := (select Project filter .id = <uuid>$project_id),
                  source := (select Source filter .id = <uuid>$source_id),
                  external_id := <str>$external_id,
                  title := <str>$title,
                  metadata := <json>$metadata,
                  created_at := <datetime>$created_at,
                }
                """,
                id=conversation.id,
                project_id=conversation.project_id,
                source_id=conversation.source_id,
                external_id=conversation.external_id,
                title=conversation.title,
                metadata=_json(conversation.metadata),
                created_at=conversation.created_at,
            )
        except gel_errors.EdgeDBError as error:
            raise _constraint_error(
                error, "conversation project/source does not exist or id already exists"
            ) from error

    async def get_conversation(
        self, project_id: UUID, external_id: str
    ) -> Conversation | None:
        row = await self._tx.query_single(
            """
            select Conversation {
              id, external_id, title, metadata, created_at,
              project: { id }, source: { id },
            }
            filter .project.id = <uuid>$project_id and .external_id = <str>$external_id
            limit 1
            """,
            project_id=project_id,
            external_id=external_id,
        )
        if row is None:
            return None
        return Conversation(
            project_id=row.project.id,
            source_id=row.source.id,
            external_id=row.external_id,
            title=row.title,
            metadata=_mapping(row.metadata),
            id=row.id,
            created_at=row.created_at,
        )

    async def add_message(self, message: ConversationMessage) -> None:
        try:
            await self._tx.execute(
                """
                insert ConversationMessage {
                  id := <uuid>$id,
                  conversation := (select Conversation filter .id = <uuid>$conversation_id),
                  external_id := <str>$external_id,
                  role := <str>$role,
                  content := <str>$content,
                  ordinal := <int32>$ordinal,
                  content_hash := <str>$content_hash,
                  created_at := <datetime>$created_at,
                  parent_external_id := <optional str>$parent_external_id,
                  attachments := <json>$attachments,
                }
                """,
                id=message.id,
                conversation_id=message.conversation_id,
                external_id=message.external_id,
                role=message.role,
                content=message.content,
                ordinal=message.ordinal,
                content_hash=message.content_hash,
                created_at=message.created_at,
                parent_external_id=message.parent_external_id,
                attachments=json.dumps(
                    list(message.attachments), ensure_ascii=False, default=str
                ),
            )
        except gel_errors.EdgeDBError as error:
            raise _constraint_error(
                error, "conversation does not exist or message id already exists"
            ) from error

    async def get_message(
        self, conversation_id: UUID, external_id: str
    ) -> ConversationMessage | None:
        row = await self._tx.query_single(
            """
            select ConversationMessage {
              id, external_id, role, content, ordinal, content_hash,
              created_at, parent_external_id, attachments,
              conversation: { id },
            }
            filter .conversation.id = <uuid>$conversation_id
               and .external_id = <str>$external_id
            limit 1
            """,
            conversation_id=conversation_id,
            external_id=external_id,
        )
        if row is None:
            return None
        return ConversationMessage(
            conversation_id=row.conversation.id,
            external_id=row.external_id,
            role=row.role,
            content=row.content,
            ordinal=row.ordinal,
            content_hash=row.content_hash,
            created_at=row.created_at,
            parent_external_id=row.parent_external_id,
            attachments=_mappings(row.attachments),
            id=row.id,
        )

    async def add_version(self, version: SourceVersion) -> None:
        try:
            await self._tx.execute(
                """
                insert SourceVersion {
                  id := <uuid>$id,
                  source := (select Source filter .id = <uuid>$source_id),
                  version := <int16>$version,
                  content_hash := <str>$content_hash,
                  object_key := <str>$object_key,
                  created_at := <datetime>$created_at,
                }
                """,
                id=version.id,
                source_id=version.source_id,
                version=version.version,
                content_hash=version.content_hash,
                object_key=version.object_key,
                created_at=version.created_at,
            )
        except gel_errors.EdgeDBError as error:
            raise _constraint_error(
                error,
                "source version parent does not exist or version/content hash already exists",
            ) from error

    async def get_version(self, version_id: UUID) -> SourceVersion | None:
        row = await self._tx.query_single(
            """
            select SourceVersion {
              id, version, content_hash, object_key, created_at, source: { id },
            }
            filter .id = <uuid>$id
            limit 1
            """,
            id=version_id,
        )
        if row is None:
            return None
        return SourceVersion(
            source_id=row.source.id,
            version=row.version,
            content_hash=row.content_hash,
            object_key=row.object_key,
            id=row.id,
            created_at=row.created_at,
        )

    async def get_version_in_project(
        self, project_id: UUID, version_id: UUID
    ) -> SourceVersion | None:
        row = await self._tx.query_single(
            """
            select SourceVersion {
              id, version, content_hash, object_key, created_at, source: { id },
            }
            filter .id = <uuid>$version_id
               and .source.project.id = <uuid>$project_id
            limit 1
            """,
            version_id=version_id,
            project_id=project_id,
        )
        if row is None:
            return None
        return SourceVersion(
            source_id=row.source.id,
            version=row.version,
            content_hash=row.content_hash,
            object_key=row.object_key,
            id=row.id,
            created_at=row.created_at,
        )

    async def get_pdf_version_by_hash(
        self, project_id: UUID, content_hash: str
    ) -> SourceVersion | None:
        row = await self._tx.query_single(
            """
            select SourceVersion {
              id, version, content_hash, object_key, created_at, source: { id },
            }
            filter .source.project.id = <uuid>$project_id
               and .source.kind = default::SourceKind.pdf
               and .content_hash = <str>$content_hash
            order by .created_at asc
            limit 1
            """,
            project_id=project_id,
            content_hash=content_hash,
        )
        if row is None:
            return None
        return SourceVersion(
            source_id=row.source.id,
            version=row.version,
            content_hash=row.content_hash,
            object_key=row.object_key,
            id=row.id,
            created_at=row.created_at,
        )

    async def next_version_number(self, source_id: UUID) -> int:
        value = await self._tx.query_single(
            """
            select (
                max((select SourceVersion
                     filter .source.id = <uuid>$source_id).version) ?? <int16>0
            ) + <int16>1
            """,
            source_id=source_id,
        )
        return int(value)

    async def add_block(self, block: ContentBlock) -> None:
        try:
            await self._tx.execute(
                """
                insert ContentBlock {
                  id := <uuid>$id,
                  source_version := (select SourceVersion filter .id = <uuid>$source_version_id),
                  ordinal := <int32>$ordinal,
                  content := <str>$content,
                  content_hash := <str>$content_hash,
                  locator := <json>$locator,
                }
                """,
                id=block.id,
                source_version_id=block.source_version_id,
                ordinal=block.ordinal,
                content=block.content,
                content_hash=block.content_hash,
                locator=_json(block.locator),
            )
        except gel_errors.EdgeDBError as error:
            raise _constraint_error(
                error, "content block source version does not exist or ordinal already exists"
            ) from error

    async def get_block(self, block_id: UUID) -> ContentBlock | None:
        row = await self._tx.query_single(
            """
            select ContentBlock {
              id, ordinal, content, content_hash, locator, source_version: { id },
            }
            filter .id = <uuid>$id
            limit 1
            """,
            id=block_id,
        )
        if row is None:
            return None
        return ContentBlock(
            source_version_id=row.source_version.id,
            ordinal=row.ordinal,
            content=row.content,
            content_hash=row.content_hash,
            locator=_mapping(row.locator),
            id=row.id,
        )

    async def list_blocks(self, source_version_id: UUID) -> list[ContentBlock]:
        rows = await self._tx.query(
            """
            select ContentBlock {
              id, ordinal, content, content_hash, locator, source_version: { id },
            }
            filter .source_version.id = <uuid>$source_version_id
            order by .ordinal asc
            """,
            source_version_id=source_version_id,
        )
        return [
            ContentBlock(
                source_version_id=row.source_version.id,
                ordinal=row.ordinal,
                content=row.content,
                content_hash=row.content_hash,
                locator=_mapping(row.locator),
                id=row.id,
            )
            for row in rows
        ]


class GelKnowledgeRepository:
    def __init__(self, tx: Any) -> None:
        self._tx = tx

    async def add_node(self, node: KnowledgeNode) -> None:
        try:
            await self._tx.execute(
                """
                insert KnowledgeNode {
                  id := <uuid>$id,
                  project := (select Project filter .id = <uuid>$project_id),
                  node_type := <str>$node_type,
                  title := <str>$title,
                  properties := <json>$properties,
                  status := <default::VerificationStatus>$status,
                  created_at := <datetime>$created_at,
                }
                """,
                id=node.id,
                project_id=node.project_id,
                node_type=node.node_type,
                title=node.title,
                properties=_json(node.properties),
                status=node.status.value,
                created_at=node.created_at,
            )
        except gel_errors.EdgeDBError as error:
            raise _constraint_error(error, "knowledge node project does not exist") from error

    async def get_node(self, node_id: UUID) -> KnowledgeNode | None:
        row = await self._tx.query_single(
            """
            select KnowledgeNode {
              id, node_type, title, properties, status, created_at, project: { id },
            }
            filter .id = <uuid>$id
            limit 1
            """,
            id=node_id,
        )
        if row is None:
            return None
        return KnowledgeNode(
            project_id=row.project.id,
            node_type=row.node_type,
            title=row.title,
            properties=_mapping(row.properties),
            status=VerificationStatus(row.status),
            id=row.id,
            created_at=row.created_at,
        )

    async def save_node(self, node: KnowledgeNode) -> None:
        try:
            rows = await self._tx.query(
                """
                update KnowledgeNode
                filter .id = <uuid>$id
                set {
                  properties := <json>$properties,
                  status := <default::VerificationStatus>$status,
                }
                """,
                id=node.id,
                properties=_json(node.properties),
                status=node.status.value,
            )
        except gel_errors.EdgeDBError as error:
            raise _constraint_error(error, "knowledge node update failed") from error
        if not rows:
            raise DomainValidationError("knowledge node does not exist")

    async def add_citation(self, citation: Citation) -> None:
        try:
            await self._tx.execute(
                """
                insert Citation {
                  id := <uuid>$id,
                  content_block := (select ContentBlock filter .id = <uuid>$content_block_id),
                  quote := <str>$quote,
                  locator := <json>$locator,
                  metadata := <json>$metadata,
                }
                """,
                id=citation.id,
                content_block_id=citation.content_block_id,
                quote=citation.quote,
                locator=_json(citation.locator),
                metadata=_json(citation.metadata),
            )
        except gel_errors.EdgeDBError as error:
            raise _constraint_error(error, "citation content block does not exist") from error

    async def get_citation(self, citation_id: UUID) -> Citation | None:
        row = await self._tx.query_single(
            """
            select Citation {
              id, quote, locator, metadata, content_block: { id },
            }
            filter .id = <uuid>$id
            limit 1
            """,
            id=citation_id,
        )
        if row is None:
            return None
        return Citation(
            content_block_id=row.content_block.id,
            quote=row.quote,
            locator=_mapping(row.locator),
            id=row.id,
            metadata=_mapping(row.metadata),
        )

    async def add_claim(self, claim: Claim) -> None:
        try:
            await self._tx.execute(
                """
                insert Claim {
                  id := <uuid>$id,
                  project := (select Project filter .id = <uuid>$project_id),
                  subject := (select KnowledgeNode filter .id = <uuid>$subject_id),
                  statement := <str>$statement,
                  confidence := <optional float32>$confidence,
                  status := <default::VerificationStatus>$status,
                  metadata := <json>$metadata,
                  citations := (select Citation
                                filter .id in array_unpack(<array<uuid>>$citation_ids)),
                  created_at := <datetime>$created_at,
                }
                """,
                id=claim.id,
                project_id=claim.project_id,
                subject_id=claim.subject_id,
                statement=claim.statement,
                confidence=claim.confidence,
                status=claim.status.value,
                metadata=_json(claim.metadata),
                citation_ids=[citation.id for citation in claim.citations],
                created_at=claim.created_at,
            )
        except gel_errors.EdgeDBError as error:
            raise _constraint_error(
                error, "claim project, subject, or citation does not exist"
            ) from error

    async def get_claim(self, claim_id: UUID) -> Claim | None:
        row = await self._tx.query_single(
            """
            select Claim {
              id, statement, confidence, status, metadata, created_at,
              project: { id }, subject: { id },
              citations: { id, quote, locator, metadata, content_block: { id } },
            }
            filter .id = <uuid>$id
            limit 1
            """,
            id=claim_id,
        )
        if row is None:
            return None
        return Claim(
            project_id=row.project.id,
            subject_id=row.subject.id,
            statement=row.statement,
            citations=tuple(
                Citation(
                    content_block_id=item.content_block.id,
                    quote=item.quote,
                    locator=_mapping(item.locator),
                    id=item.id,
                    metadata=_mapping(item.metadata),
                )
                for item in row.citations
            ),
            confidence=row.confidence,
            status=VerificationStatus(row.status),
            id=row.id,
            created_at=row.created_at,
            metadata=_mapping(row.metadata),
        )

    async def save_claim(self, claim: Claim) -> None:
        try:
            rows = await self._tx.query(
                """
                update Claim
                filter .id = <uuid>$id
                set {
                  status := <default::VerificationStatus>$status,
                  metadata := <json>$metadata,
                }
                """,
                id=claim.id,
                status=claim.status.value,
                metadata=_json(claim.metadata),
            )
        except gel_errors.EdgeDBError as error:
            raise _constraint_error(error, "claim update failed") from error
        if not rows:
            raise DomainValidationError("claim does not exist")

    async def add_relation(self, relation: Relation) -> None:
        try:
            await self._tx.execute(
                """
                insert Relation {
                  id := <uuid>$id,
                  project := (select Project filter .id = <uuid>$project_id),
                  relation_type := (select RelationType filter .key = <str>$relation_type),
                  source := (select KnowledgeNode filter .id = <uuid>$source_id),
                  target := (select KnowledgeNode filter .id = <uuid>$target_id),
                  properties := <json>$properties,
                  confidence := <optional float32>$confidence,
                  status := <default::VerificationStatus>$status,
                  metadata := <json>$metadata,
                  citations := (select Citation
                                filter .id in array_unpack(<array<uuid>>$citation_ids)),
                  created_at := <datetime>$created_at,
                }
                """,
                id=relation.id,
                project_id=relation.project_id,
                relation_type=relation.relation_type,
                source_id=relation.source_id,
                target_id=relation.target_id,
                properties=_json(relation.properties),
                confidence=relation.confidence,
                status=relation.status.value,
                metadata=_json(relation.metadata),
                citation_ids=list(relation.citation_ids),
                created_at=relation.created_at,
            )
        except gel_errors.EdgeDBError as error:
            raise _constraint_error(
                error, "relation type, endpoints, project, or citation does not exist"
            ) from error

    async def get_relation(self, relation_id: UUID) -> Relation | None:
        row = await self._tx.query_single(
            """
            select Relation {
              id, properties, confidence, status, metadata, created_at,
              project: { id }, source: { id }, target: { id },
              relation_type: { key },
              citations: { id },
            }
            filter .id = <uuid>$id
            limit 1
            """,
            id=relation_id,
        )
        if row is None:
            return None
        return Relation(
            project_id=row.project.id,
            relation_type=row.relation_type.key,
            source_id=row.source.id,
            target_id=row.target.id,
            citation_ids=tuple(item.id for item in row.citations),
            properties=_mapping(row.properties),
            confidence=row.confidence,
            id=row.id,
            created_at=row.created_at,
            status=VerificationStatus(row.status),
            metadata=_mapping(row.metadata),
        )

    async def save_relation(self, relation: Relation) -> None:
        try:
            rows = await self._tx.query(
                """
                update Relation
                filter .id = <uuid>$id
                set {
                  properties := <json>$properties,
                  confidence := <optional float32>$confidence,
                  status := <default::VerificationStatus>$status,
                  metadata := <json>$metadata,
                }
                """,
                id=relation.id,
                properties=_json(relation.properties),
                confidence=relation.confidence,
                status=relation.status.value,
                metadata=_json(relation.metadata),
            )
        except gel_errors.EdgeDBError as error:
            raise _constraint_error(error, "relation update failed") from error
        if not rows:
            raise DomainValidationError("relation does not exist")

    async def add_relation_type(self, relation_type: RelationType) -> None:
        try:
            await self._tx.execute(
                """
                insert RelationType {
                  key := <str>$key,
                  label := <str>$label,
                  description := <str>$description,
                  directional := <bool>$directional,
                  created_at := <datetime>$created_at,
                }
                """,
                key=relation_type.key,
                label=relation_type.label,
                description=relation_type.description,
                directional=relation_type.directional,
                created_at=_now(),
            )
        except gel_errors.EdgeDBError as error:
            raise _constraint_error(error, "relation type key already exists") from error

    async def get_relation_type(self, key: str) -> RelationType | None:
        row = await self._tx.query_single(
            """
            select RelationType { key, label, description, directional }
            filter .key = <str>$key
            limit 1
            """,
            key=key,
        )
        if row is None:
            return None
        return RelationType(
            key=row.key,
            label=row.label,
            description=row.description,
            directional=row.directional,
        )


class GelGovernanceRepository:
    def __init__(self, tx: Any) -> None:
        self._tx = tx

    async def add_run(self, run: GovernanceRun) -> None:
        try:
            await self._tx.execute(
                """
                insert GovernanceRun {
                  id := <uuid>$id,
                  project := (select Project filter .id = <uuid>$project_id),
                  task_id := <uuid>$task_id,
                  rule_version := <str>$rule_version,
                  status := <default::GovernanceRunStatus>$status,
                  candidate_ids := array_unpack(<array<uuid>>$candidate_ids),
                  created_at := <datetime>$created_at,
                }
                """,
                id=run.id,
                project_id=run.project_id,
                task_id=run.task_id,
                rule_version=run.rule_version,
                status=run.status.value,
                candidate_ids=list(run.candidate_ids),
                created_at=run.created_at,
            )
        except gel_errors.EdgeDBError as error:
            raise _constraint_error(error, "governance run project does not exist") from error

    async def add_issue(self, issue: GovernanceIssue) -> None:
        try:
            await self._tx.execute(
                """
                insert GovernanceIssue {
                  id := <uuid>$id,
                  run := (select GovernanceRun filter .id = <uuid>$run_id),
                  candidate_id := <uuid>$candidate_id,
                  candidate_kind := <default::CandidateKind>$candidate_kind,
                  code := <str>$code,
                  message := <str>$message,
                  severity := <default::GovernanceIssueSeverity>$severity,
                  created_at := <datetime>$created_at,
                }
                """,
                id=issue.id,
                run_id=issue.run_id,
                candidate_id=issue.candidate_id,
                candidate_kind=issue.candidate_kind.value,
                code=issue.code,
                message=issue.message,
                severity=issue.severity.value,
                created_at=issue.created_at,
            )
        except gel_errors.EdgeDBError as error:
            raise _constraint_error(error, "governance issue run does not exist") from error

    async def add_duplicate_group(self, group: DuplicateGroup) -> None:
        try:
            await self._tx.execute(
                """
                insert DuplicateGroup {
                  id := <uuid>$id,
                  project := (select Project filter .id = <uuid>$project_id),
                  candidate_ids := array_unpack(<array<uuid>>$candidate_ids),
                  basis := <str>$basis,
                  created_at := <datetime>$created_at,
                }
                """,
                id=group.id,
                project_id=group.project_id,
                candidate_ids=list(group.candidate_ids),
                basis=group.basis,
                created_at=group.created_at,
            )
        except gel_errors.EdgeDBError as error:
            raise _constraint_error(error, "duplicate group project does not exist") from error

    async def add_conflict(self, conflict: ConflictRecord) -> None:
        try:
            await self._tx.execute(
                """
                insert ConflictRecord {
                  id := <uuid>$id,
                  project := (select Project filter .id = <uuid>$project_id),
                  candidate_ids := array_unpack(<array<uuid>>$candidate_ids),
                  basis := <str>$basis,
                  status := <str>$status,
                  created_at := <datetime>$created_at,
                }
                """,
                id=conflict.id,
                project_id=conflict.project_id,
                candidate_ids=list(conflict.candidate_ids),
                basis=conflict.basis,
                status=conflict.status,
                created_at=conflict.created_at,
            )
        except gel_errors.EdgeDBError as error:
            raise _constraint_error(error, "conflict project does not exist") from error

    async def add_review_task(self, task: ReviewTask) -> None:
        try:
            await self._tx.execute(
                """
                insert ReviewTask {
                  id := <uuid>$id,
                  run := (select GovernanceRun filter .id = <uuid>$run_id),
                  candidate_id := <uuid>$candidate_id,
                  candidate_kind := <default::CandidateKind>$candidate_kind,
                  status := <default::ReviewTaskStatus>$status,
                  reviewer_id := <optional str>$reviewer_id,
                  reason := <optional str>$reason,
                  before := <json>$before,
                  after := <json>$after,
                  version := <int32>$version,
                  reviewed_at := <optional datetime>$reviewed_at,
                  created_at := <datetime>$created_at,
                }
                """,
                id=task.id,
                run_id=task.run_id,
                candidate_id=task.candidate_id,
                candidate_kind=task.candidate_kind.value,
                status=task.status.value,
                reviewer_id=task.reviewer_id,
                reason=task.reason,
                before=_json(task.before),
                after=_json(task.after),
                version=task.version,
                reviewed_at=task.reviewed_at,
                created_at=task.created_at,
            )
        except gel_errors.EdgeDBError as error:
            raise _constraint_error(error, "review task governance run does not exist") from error

    async def get_review_task(self, task_id: UUID) -> ReviewTask | None:
        row = await self._tx.query_single(
            """
            select ReviewTask {
              id, candidate_id, candidate_kind, status, reviewer_id, reason,
              before, after, version, created_at, reviewed_at, run: { id },
            }
            filter .id = <uuid>$id
            limit 1
            """,
            id=task_id,
        )
        if row is None:
            return None
        return ReviewTask(
            run_id=row.run.id,
            candidate_id=row.candidate_id,
            candidate_kind=CandidateKind(row.candidate_kind),
            status=ReviewTaskStatus(row.status),
            reviewer_id=row.reviewer_id,
            reason=row.reason,
            before=_mapping(row.before),
            after=_mapping(row.after),
            version=row.version,
            id=row.id,
            created_at=row.created_at,
            reviewed_at=row.reviewed_at,
        )

    async def save_review_task(self, task: ReviewTask) -> None:
        try:
            rows = await self._tx.query(
                """
                update ReviewTask
                filter .id = <uuid>$id
                set {
                  status := <default::ReviewTaskStatus>$status,
                  reviewer_id := <optional str>$reviewer_id,
                  reason := <optional str>$reason,
                  before := <json>$before,
                  after := <json>$after,
                  version := <int32>$version,
                  reviewed_at := <optional datetime>$reviewed_at,
                }
                """,
                id=task.id,
                status=task.status.value,
                reviewer_id=task.reviewer_id,
                reason=task.reason,
                before=_json(task.before),
                after=_json(task.after),
                version=task.version,
                reviewed_at=task.reviewed_at,
            )
        except gel_errors.EdgeDBError as error:
            raise _constraint_error(error, "review task update failed") from error
        if not rows:
            raise DomainValidationError("review task does not exist")

    async def list_review_tasks(self, *, limit: int = 100) -> list[ReviewTask]:
        rows = await self._tx.query(
            """
            select ReviewTask {
              id, candidate_id, candidate_kind, status, reviewer_id, reason,
              before, after, version, created_at, reviewed_at, run: { id },
            }
            order by .created_at desc
            limit <int64>$limit
            """,
            limit=limit,
        )
        return [
            ReviewTask(
                run_id=row.run.id,
                candidate_id=row.candidate_id,
                candidate_kind=CandidateKind(row.candidate_kind),
                status=ReviewTaskStatus(row.status),
                reviewer_id=row.reviewer_id,
                reason=row.reason,
                before=_mapping(row.before),
                after=_mapping(row.after),
                version=row.version,
                id=row.id,
                created_at=row.created_at,
                reviewed_at=row.reviewed_at,
            )
            for row in rows
        ]


class GelWritebackRepository(WritebackRepository):
    def __init__(self, tx: Any) -> None:
        self._tx = tx

    @staticmethod
    def _values(record: WritebackRecord) -> dict[str, Any]:
        return {
            "id": record.id,
            "project_id": record.project_id,
            "governance_run_id": record.governance_run_id,
            "schema_namespace": record.schema_namespace,
            "schema_version": record.schema_version,
            "idempotency_key": record.idempotency_key,
            "request_digest": record.request_digest,
            "candidate_digest": record.candidate_digest,
            "candidates": _json(
                [
                    {
                        "candidate_id": str(item.candidate_id),
                        "candidate_kind": item.candidate_kind.value,
                        "expected_review_version": item.expected_review_version,
                    }
                    for item in record.candidates
                ]
            ),
            "status": record.status.value,
            "effects_job_id": record.effects_job_id,
            "okf_object_key": record.okf_object_key,
            "index_job_id": record.index_job_id,
            "error_code": record.error_code,
            "error_digest": record.error_digest,
            "created_at": record.created_at,
            "committed_at": record.committed_at,
            "completed_at": record.completed_at,
        }

    async def add(self, record: WritebackRecord) -> None:
        try:
            await self._tx.execute(
                """
                insert WritebackRecord {
                  id := <uuid>$id,
                  project := (select Project filter .id = <uuid>$project_id),
                  governance_run := (select GovernanceRun filter .id = <uuid>$governance_run_id),
                  schema_namespace := <str>$schema_namespace,
                  schema_version := <int32>$schema_version,
                  idempotency_key := <str>$idempotency_key,
                  request_digest := <str>$request_digest,
                  candidate_digest := <str>$candidate_digest,
                  candidates := <json>$candidates,
                  status := <default::WritebackStatus>$status,
                  effects_job_id := <optional uuid>$effects_job_id,
                  okf_object_key := <optional str>$okf_object_key,
                  index_job_id := <optional uuid>$index_job_id,
                  error_code := <optional str>$error_code,
                  error_digest := <optional str>$error_digest,
                  created_at := <datetime>$created_at,
                  committed_at := <optional datetime>$committed_at,
                  completed_at := <optional datetime>$completed_at,
                }
                """,
                **self._values(record),
            )
        except gel_errors.EdgeDBError as error:
            raise _constraint_error(
                error, "writeback idempotency key or parent already exists"
            ) from error

    async def get(self, record_id: UUID) -> WritebackRecord | None:
        row = await self._tx.query_single(
            """
            select WritebackRecord {
              id, schema_namespace, schema_version, idempotency_key, request_digest,
              candidate_digest, candidates, status, effects_job_id, okf_object_key,
              index_job_id, error_code, error_digest, created_at, committed_at, completed_at,
              project: { id }, governance_run: { id },
            }
            filter .id = <uuid>$id
            limit 1
            """,
            id=record_id,
        )
        return _writeback_from_row(row) if row is not None else None

    async def get_by_idempotency_key(self, key: str) -> WritebackRecord | None:
        row = await self._tx.query_single(
            """
            select WritebackRecord {
              id, schema_namespace, schema_version, idempotency_key, request_digest,
              candidate_digest, candidates, status, effects_job_id, okf_object_key,
              index_job_id, error_code, error_digest, created_at, committed_at, completed_at,
              project: { id }, governance_run: { id },
            }
            filter .idempotency_key = <str>$key
            limit 1
            """,
            key=key,
        )
        return _writeback_from_row(row) if row is not None else None

    async def save(self, record: WritebackRecord) -> None:
        try:
            rows = await self._tx.query(
                """
                update WritebackRecord
                filter .id = <uuid>$id
                set {
                  status := <default::WritebackStatus>$status,
                  effects_job_id := <optional uuid>$effects_job_id,
                  okf_object_key := <optional str>$okf_object_key,
                  index_job_id := <optional uuid>$index_job_id,
                  error_code := <optional str>$error_code,
                  error_digest := <optional str>$error_digest,
                  committed_at := <optional datetime>$committed_at,
                  completed_at := <optional datetime>$completed_at,
                }
                """,
                id=record.id,
                status=record.status.value,
                effects_job_id=record.effects_job_id,
                okf_object_key=record.okf_object_key,
                index_job_id=record.index_job_id,
                error_code=record.error_code,
                error_digest=record.error_digest,
                committed_at=record.committed_at,
                completed_at=record.completed_at,
            )
        except gel_errors.EdgeDBError as error:
            raise _constraint_error(error, "writeback record update failed") from error
        if not rows:
            raise DomainValidationError("writeback record does not exist")

    async def add_item(self, item: WritebackItem) -> None:
        try:
            await self._tx.execute(
                """
                insert WritebackItem {
                  id := <uuid>$id,
                  record := (select WritebackRecord filter .id = <uuid>$record_id),
                  candidate_id := <uuid>$candidate_id,
                  candidate_kind := <default::CandidateKind>$candidate_kind,
                  before_status := <default::VerificationStatus>$before_status,
                  after_status := <default::VerificationStatus>$after_status,
                  before_digest := <str>$before_digest,
                  after_digest := <str>$after_digest,
                  result := <str>$result,
                  created_at := <datetime>$created_at,
                }
                """,
                id=item.id,
                record_id=item.record_id,
                candidate_id=item.candidate_id,
                candidate_kind=item.candidate_kind.value,
                before_status=item.before_status.value,
                after_status=item.after_status.value,
                before_digest=item.before_digest,
                after_digest=item.after_digest,
                result=item.result,
                created_at=item.created_at,
            )
        except gel_errors.EdgeDBError as error:
            raise _constraint_error(
                error, "writeback item record does not exist or already exists"
            ) from error

    async def list_items(self, record_id: UUID) -> list[WritebackItem]:
        rows = await self._tx.query(
            """
            select WritebackItem {
              id, candidate_id, candidate_kind, before_status, after_status,
              before_digest, after_digest, result, created_at,
            }
            filter .record.id = <uuid>$record_id
            order by .created_at asc
            """,
            record_id=record_id,
        )
        return [
            WritebackItem(
                record_id=record_id,
                candidate_id=row.candidate_id,
                candidate_kind=CandidateKind(row.candidate_kind),
                before_status=VerificationStatus(row.before_status),
                after_status=VerificationStatus(row.after_status),
                before_digest=row.before_digest,
                after_digest=row.after_digest,
                result=row.result,
                id=row.id,
                created_at=row.created_at,
            )
            for row in rows
        ]


def _writeback_from_row(row: Any) -> WritebackRecord:
    return WritebackRecord(
        project_id=row.project.id,
        governance_run_id=row.governance_run.id,
        schema_namespace=row.schema_namespace,
        schema_version=row.schema_version,
        idempotency_key=row.idempotency_key,
        request_digest=row.request_digest,
        candidate_digest=row.candidate_digest,
        candidates=_candidate_refs(row.candidates),
        status=WritebackStatus(row.status),
        effects_job_id=row.effects_job_id,
        okf_object_key=row.okf_object_key,
        index_job_id=row.index_job_id,
        error_code=row.error_code,
        error_digest=row.error_digest,
        id=row.id,
        created_at=row.created_at,
        committed_at=row.committed_at,
        completed_at=row.completed_at,
    )


class GelJobRepository:
    def __init__(self, tx: Any) -> None:
        self._tx = tx

    async def add(self, job: Job) -> None:
        try:
            await self._tx.execute(
                """
                insert Job {
                  id := <uuid>$id,
                  kind := <str>$kind,
                  idempotency_key := <str>$idempotency_key,
                  payload := <json>$payload,
                  status := <default::JobStatus>$status,
                  progress := <int16>$progress,
                  stage := <str>$stage,
                  attempt := <int16>$attempt,
                  max_attempts := <int16>$max_attempts,
                  timeout_seconds := <int32>$timeout_seconds,
                  failure_reason := <optional str>$failure_reason,
                  next_attempt_at := <optional datetime>$next_attempt_at,
                  created_at := <datetime>$created_at,
                  started_at := <optional datetime>$started_at,
                  finished_at := <optional datetime>$finished_at,
                }
                """,
                **self._values(job),
            )
        except gel_errors.EdgeDBError as error:
            raise _constraint_error(error, "job idempotency key already exists") from error

    async def save(self, job: Job) -> None:
        try:
            rows = await self._tx.query(
                """
                update Job
                filter .id = <uuid>$id
                set {
                  kind := <str>$kind,
                  idempotency_key := <str>$idempotency_key,
                  payload := <json>$payload,
                  status := <default::JobStatus>$status,
                  progress := <int16>$progress,
                  stage := <str>$stage,
                  attempt := <int16>$attempt,
                  max_attempts := <int16>$max_attempts,
                  timeout_seconds := <int32>$timeout_seconds,
                  failure_reason := <optional str>$failure_reason,
                  next_attempt_at := <optional datetime>$next_attempt_at,
                  created_at := <datetime>$created_at,
                  started_at := <optional datetime>$started_at,
                  finished_at := <optional datetime>$finished_at,
                }
                """,
                id=job.id,
                **self._values_without_id(job),
            )
        except gel_errors.EdgeDBError as error:
            raise _constraint_error(error, "job update failed") from error
        if not rows:
            raise DomainValidationError("job does not exist")

    _JOB_SHAPE = """{
      id, kind, idempotency_key, payload, status, progress, stage, attempt,
      max_attempts, timeout_seconds, failure_reason, next_attempt_at,
      created_at, started_at, finished_at,
    }"""

    async def get(self, job_id: UUID) -> Job | None:
        row = await self._tx.query_single(
            f"select Job {GelJobRepository._JOB_SHAPE} filter .id = <uuid>$id limit 1",
            id=job_id,
        )
        return self._from_row(row) if row is not None else None

    async def get_by_idempotency_key(self, key: str) -> Job | None:
        row = await self._tx.query_single(
            f"""
            select Job {GelJobRepository._JOB_SHAPE}
            filter .idempotency_key = <str>$key
            limit 1
            """,
            key=key,
        )
        return self._from_row(row) if row is not None else None

    async def list(self, *, limit: int = 100) -> list[Job]:
        rows = await self._tx.query(
            (
                "select Job "
                f"{GelJobRepository._JOB_SHAPE}"
                " order by .created_at desc limit <int64>$limit"
            ),
            limit=limit,
        )
        return [self._from_row(row) for row in rows]

    @staticmethod
    def _values(job: Job) -> dict[str, Any]:
        return {"id": job.id, **GelJobRepository._values_without_id(job)}

    @staticmethod
    def _values_without_id(job: Job) -> dict[str, Any]:
        return {
            "kind": job.kind,
            "idempotency_key": job.idempotency_key,
            "payload": _json(job.payload),
            "status": job.status.value,
            "progress": job.progress,
            "stage": job.stage,
            "attempt": job.attempt,
            "max_attempts": job.max_attempts,
            "timeout_seconds": job.timeout_seconds,
            "failure_reason": job.failure_reason,
            "next_attempt_at": job.next_attempt_at,
            "created_at": job.created_at,
            "started_at": job.started_at,
            "finished_at": job.finished_at,
        }

    @staticmethod
    def _from_row(row: Any) -> Job:
        return Job(
            kind=row.kind,
            idempotency_key=row.idempotency_key,
            payload=_mapping(row.payload),
            max_attempts=row.max_attempts,
            timeout_seconds=row.timeout_seconds,
            id=row.id,
            status=JobStatus(row.status),
            progress=row.progress,
            stage=row.stage,
            attempt=row.attempt,
            failure_reason=row.failure_reason,
            next_attempt_at=row.next_attempt_at,
            created_at=row.created_at,
            started_at=row.started_at,
            finished_at=row.finished_at,
        )


class GelUnitOfWork:
    def __init__(self, store: GelStore) -> None:
        self._store = store
        self._retry: Any | None = None
        self._tx: Any | None = None
        self.sources: SourceRepository
        self.knowledge: KnowledgeRepository
        self.governance: GovernanceRepository
        self.writebacks: WritebackRepository
        self.jobs: JobRepository
        self._committed = False

    async def __aenter__(self) -> Self:
        # ``client.transaction()`` is an async retry iterator: each iteration
        # yields a managed transaction that commits on clean exit and rolls
        # back on exception. We take one iteration and drive it manually so
        # commit/rollback happens exactly at ``__aexit__`` (matching the
        # SQLite UoW semantics).
        retry: Any = self._store.client.transaction()
        self._retry = retry
        tx = await retry.__anext__()
        self._tx = tx
        await tx.__aenter__()
        self.sources = GelSourceRepository(tx)
        self.knowledge = GelKnowledgeRepository(tx)
        self.governance = GelGovernanceRepository(tx)
        self.writebacks = GelWritebackRepository(tx)
        self.jobs = GelJobRepository(tx)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        tx = self._tx
        self._retry = None
        self._tx = None
        if tx is None:
            return
        if not self._committed and exc_type is None:
            # Force a rollback: pass a synthetic exception to the transaction
            # context manager so it rolls back without re-raising anything.
            exc_type, exc, traceback = (_Rollback, _Rollback(), None)
        await tx.__aexit__(exc_type, exc, traceback)

    async def commit(self) -> None:
        self._committed = True

    async def rollback(self) -> None:
        self._committed = False


class GelUnitOfWorkFactory:
    def __init__(self, store: GelStore) -> None:
        self.store = store

    def __call__(self) -> GelUnitOfWork:
        return GelUnitOfWork(self.store)


class GelJobQueue(JobQueue):
    """Durable queue view backed by the committed Job rows in Gel.

    Enqueue is intentionally a no-op: the committed job row is the queue,
    exactly like ``SQLiteJobQueue``. This lets an API process and a separately
    started worker share work against the same Gel database.
    """

    def __init__(self, store: GelStore, poll_interval_seconds: float = 0.25) -> None:
        self._store = store
        self._poll_interval_seconds = poll_interval_seconds

    async def enqueue(self, job_id: UUID) -> None:
        return None

    async def dequeue(self, *, timeout_seconds: float | None = None) -> UUID | None:
        deadline = monotonic() + timeout_seconds if timeout_seconds is not None else None
        while True:
            row = await self._store.client.query_single(
                """
                select Job { id }
                filter (
                  .status = default::JobStatus.queued
                  or (
                    .status = default::JobStatus.retrying
                    and (
                      (.next_attempt_at ?? <datetime>'1970-01-01T00:00:00Z')
                      <= <datetime>$now
                    )
                  )
                )
                order by .created_at asc
                limit 1
                """,
                now=_now(),
            )
            if row is not None:
                return cast(UUID, row.id)
            if deadline is not None and monotonic() >= deadline:
                return None
            await asyncio.sleep(self._poll_interval_seconds)
