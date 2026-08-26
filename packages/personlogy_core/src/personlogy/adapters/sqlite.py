"""SQLite persistence adapters for local development and single-node execution."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from types import TracebackType
from typing import cast
from uuid import UUID

from personlogy.domain.job import Job, JobStatus
from personlogy.domain.knowledge.models import Citation, Claim, KnowledgeNode
from personlogy.domain.relation.models import Relation, RelationType
from personlogy.domain.source.conversation import Conversation, ConversationMessage
from personlogy.domain.source.models import (
    ContentBlock,
    Project,
    Source,
    SourceKind,
    SourceVersion,
)
from personlogy.ports.queue import JobQueue
from personlogy.ports.repositories import JobRepository, KnowledgeRepository, SourceRepository
from personlogy.ports.unit_of_work import UnitOfWork
from personlogy.shared.errors import DomainValidationError

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS project (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS source (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES project(id),
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS conversation (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES project(id),
    source_id TEXT NOT NULL REFERENCES source(id),
    external_id TEXT NOT NULL,
    title TEXT NOT NULL,
    metadata TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(project_id, external_id)
);
CREATE TABLE IF NOT EXISTS conversation_message (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversation(id),
    external_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    content_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    parent_external_id TEXT,
    attachments TEXT NOT NULL,
    UNIQUE(conversation_id, external_id)
);
CREATE TABLE IF NOT EXISTS source_version (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES source(id),
    version INTEGER NOT NULL,
    content_hash TEXT NOT NULL,
    object_key TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(source_id, content_hash),
    UNIQUE(source_id, version)
);
CREATE TABLE IF NOT EXISTS content_block (
    id TEXT PRIMARY KEY,
    source_version_id TEXT NOT NULL REFERENCES source_version(id),
    ordinal INTEGER NOT NULL,
    content TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    locator TEXT NOT NULL,
    UNIQUE(source_version_id, ordinal)
);
CREATE TABLE IF NOT EXISTS knowledge_node (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES project(id),
    node_type TEXT NOT NULL,
    title TEXT NOT NULL,
    properties TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS citation (
    id TEXT PRIMARY KEY,
    content_block_id TEXT NOT NULL REFERENCES content_block(id),
    quote TEXT NOT NULL,
    locator TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS claim (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES project(id),
    subject_id TEXT NOT NULL REFERENCES knowledge_node(id),
    statement TEXT NOT NULL,
    confidence REAL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS claim_citation (
    claim_id TEXT NOT NULL REFERENCES claim(id),
    citation_id TEXT NOT NULL REFERENCES citation(id),
    PRIMARY KEY(claim_id, citation_id)
);
CREATE TABLE IF NOT EXISTS relation_type (
    key TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    description TEXT NOT NULL,
    directional INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS relation (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES project(id),
    relation_type TEXT NOT NULL REFERENCES relation_type(key),
    source_id TEXT NOT NULL REFERENCES knowledge_node(id),
    target_id TEXT NOT NULL REFERENCES knowledge_node(id),
    properties TEXT NOT NULL,
    confidence REAL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS relation_citation (
    relation_id TEXT NOT NULL REFERENCES relation(id),
    citation_id TEXT NOT NULL REFERENCES citation(id),
    PRIMARY KEY(relation_id, citation_id)
);
CREATE TABLE IF NOT EXISTS job (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    payload TEXT NOT NULL,
    status TEXT NOT NULL,
    progress INTEGER NOT NULL,
    stage TEXT NOT NULL,
    attempt INTEGER NOT NULL,
    max_attempts INTEGER NOT NULL,
    timeout_seconds INTEGER NOT NULL,
    failure_reason TEXT,
    next_attempt_at TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);
CREATE INDEX IF NOT EXISTS job_ready_idx
    ON job(status, next_attempt_at, created_at);
"""


def _json(value: dict[str, object]) -> str:
    return _json_value(value)


def _json_value(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def _mapping(value: str) -> dict[str, object]:
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("stored JSON value is not an object")
    return cast(dict[str, object], parsed)


def _mappings(value: str) -> tuple[dict[str, object], ...]:
    parsed = json.loads(value)
    if not isinstance(parsed, list):
        raise ValueError("stored JSON value is not a list")
    return tuple(cast(dict[str, object], item) for item in parsed)


def _timestamp(value: datetime) -> str:
    return value.isoformat()


def _datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value is not None else None


def _required_datetime(value: str) -> datetime:
    parsed = _datetime(value)
    if parsed is None:
        raise ValueError("required timestamp is missing")
    return parsed


def _id(value: UUID) -> str:
    return str(value)


class SQLiteStore:
    """Database handle shared by UoW and queue instances."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        connection = self.connect()
        try:
            connection.executescript(SCHEMA)
        finally:
            connection.close()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection


class SQLiteSourceRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    async def add_project(self, project: Project) -> None:
        try:
            self._connection.execute(
                "INSERT INTO project (id, name, slug, created_at) VALUES (?, ?, ?, ?)",
                (_id(project.id), project.name, project.slug, _timestamp(project.created_at)),
            )
        except sqlite3.IntegrityError as error:
            raise DomainValidationError("project slug already exists") from error

    async def get_project_by_slug(self, slug: str) -> Project | None:
        row = self._connection.execute(
            "SELECT * FROM project WHERE slug = ?", (slug,)
        ).fetchone()
        if row is None:
            return None
        return Project(
            name=row["name"], slug=row["slug"], id=UUID(row["id"]),
            created_at=_required_datetime(row["created_at"]),
        )

    async def add_source(self, source: Source) -> None:
        try:
            self._connection.execute(
                "INSERT INTO source (id, project_id, kind, title, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    _id(source.id),
                    _id(source.project_id),
                    source.kind.value,
                    source.title,
                    _timestamp(source.created_at),
                ),
            )
        except sqlite3.IntegrityError as error:
            raise DomainValidationError("source project does not exist") from error

    async def get_source(
        self, project_id: UUID, kind: SourceKind, title: str
    ) -> Source | None:
        row = self._connection.execute(
            """SELECT * FROM source
               WHERE project_id = ? AND kind = ? AND title = ?
               ORDER BY created_at ASC LIMIT 1""",
            (_id(project_id), kind.value, title),
        ).fetchone()
        if row is None:
            return None
        return Source(
            project_id=UUID(row["project_id"]),
            kind=SourceKind(row["kind"]),
            title=row["title"],
            id=UUID(row["id"]),
            created_at=_required_datetime(row["created_at"]),
        )

    async def add_conversation(self, conversation: Conversation) -> None:
        try:
            self._connection.execute(
                """INSERT INTO conversation
                   (id, project_id, source_id, external_id, title, metadata, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    _id(conversation.id), _id(conversation.project_id),
                    _id(conversation.source_id), conversation.external_id,
                    conversation.title, _json(conversation.metadata),
                    _timestamp(conversation.created_at),
                ),
            )
        except sqlite3.IntegrityError as error:
            raise DomainValidationError(
                "conversation project/source does not exist or id already exists"
            ) from error

    async def get_conversation(
        self, project_id: UUID, external_id: str
    ) -> Conversation | None:
        row = self._connection.execute(
            """SELECT * FROM conversation
               WHERE project_id = ? AND external_id = ?""",
            (_id(project_id), external_id),
        ).fetchone()
        if row is None:
            return None
        return Conversation(
            project_id=UUID(row["project_id"]), source_id=UUID(row["source_id"]),
            external_id=row["external_id"], title=row["title"],
            metadata=_mapping(row["metadata"]), id=UUID(row["id"]),
            created_at=_required_datetime(row["created_at"]),
        )

    async def add_message(self, message: ConversationMessage) -> None:
        try:
            self._connection.execute(
                """INSERT INTO conversation_message
                   (id, conversation_id, external_id, role, content, ordinal,
                    content_hash, created_at, parent_external_id, attachments)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    _id(message.id), _id(message.conversation_id), message.external_id,
                    message.role, message.content, message.ordinal, message.content_hash,
                    _timestamp(message.created_at), message.parent_external_id,
                    _json_value(list(message.attachments)),
                ),
            )
        except sqlite3.IntegrityError as error:
            raise DomainValidationError(
                "conversation does not exist or message id already exists"
            ) from error

    async def get_message(
        self, conversation_id: UUID, external_id: str
    ) -> ConversationMessage | None:
        row = self._connection.execute(
            """SELECT * FROM conversation_message
               WHERE conversation_id = ? AND external_id = ?""",
            (_id(conversation_id), external_id),
        ).fetchone()
        if row is None:
            return None
        return ConversationMessage(
            conversation_id=UUID(row["conversation_id"]), external_id=row["external_id"],
            role=row["role"], content=row["content"], ordinal=row["ordinal"],
            content_hash=row["content_hash"], created_at=_required_datetime(row["created_at"]),
            parent_external_id=row["parent_external_id"],
            attachments=_mappings(row["attachments"]), id=UUID(row["id"]),
        )

    async def add_version(self, version: SourceVersion) -> None:
        try:
            self._connection.execute(
                """INSERT INTO source_version
                   (id, source_id, version, content_hash, object_key, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    _id(version.id),
                    _id(version.source_id),
                    version.version,
                    version.content_hash,
                    version.object_key,
                    _timestamp(version.created_at),
                ),
            )
        except sqlite3.IntegrityError as error:
            raise DomainValidationError(
                "source version parent does not exist or version/content hash already exists"
            ) from error

    async def get_version(self, version_id: UUID) -> SourceVersion | None:
        row = self._connection.execute(
            "SELECT * FROM source_version WHERE id = ?", (_id(version_id),)
        ).fetchone()
        if row is None:
            return None
        return SourceVersion(
            source_id=UUID(row["source_id"]),
            version=row["version"],
            content_hash=row["content_hash"],
            object_key=row["object_key"],
            id=UUID(row["id"]),
            created_at=_required_datetime(row["created_at"]),
        )

    async def get_pdf_version_by_hash(
        self, project_id: UUID, content_hash: str
    ) -> SourceVersion | None:
        row = self._connection.execute(
            """SELECT version.* FROM source_version AS version
               JOIN source ON source.id = version.source_id
               WHERE source.project_id = ? AND source.kind = 'pdf'
                 AND version.content_hash = ?
               ORDER BY version.created_at ASC LIMIT 1""",
            (_id(project_id), content_hash),
        ).fetchone()
        if row is None:
            return None
        return SourceVersion(
            source_id=UUID(row["source_id"]),
            version=row["version"],
            content_hash=row["content_hash"],
            object_key=row["object_key"],
            id=UUID(row["id"]),
            created_at=_required_datetime(row["created_at"]),
        )

    async def next_version_number(self, source_id: UUID) -> int:
        row = self._connection.execute(
            "SELECT COALESCE(MAX(version), 0) + 1 AS next_version "
            "FROM source_version WHERE source_id = ?",
            (_id(source_id),),
        ).fetchone()
        return int(row["next_version"])

    async def add_block(self, block: ContentBlock) -> None:
        try:
            self._connection.execute(
                """INSERT INTO content_block
                   (id, source_version_id, ordinal, content, content_hash, locator)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    _id(block.id),
                    _id(block.source_version_id),
                    block.ordinal,
                    block.content,
                    block.content_hash,
                    _json(block.locator),
                ),
            )
        except sqlite3.IntegrityError as error:
            raise DomainValidationError(
                "content block source version does not exist or ordinal already exists"
            ) from error

    async def list_blocks(self, source_version_id: UUID) -> list[ContentBlock]:
        rows = self._connection.execute(
            "SELECT * FROM content_block WHERE source_version_id = ? ORDER BY ordinal ASC",
            (_id(source_version_id),),
        ).fetchall()
        return [
            ContentBlock(
                source_version_id=UUID(row["source_version_id"]),
                ordinal=row["ordinal"],
                content=row["content"],
                content_hash=row["content_hash"],
                locator=_mapping(row["locator"]),
                id=UUID(row["id"]),
            )
            for row in rows
        ]


class SQLiteKnowledgeRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    async def add_node(self, node: KnowledgeNode) -> None:
        try:
            self._connection.execute(
                """INSERT INTO knowledge_node
                   (id, project_id, node_type, title, properties, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    _id(node.id),
                    _id(node.project_id),
                    node.node_type,
                    node.title,
                    _json(node.properties),
                    node.status.value,
                    _timestamp(node.created_at),
                ),
            )
        except sqlite3.IntegrityError as error:
            raise DomainValidationError("knowledge node project does not exist") from error

    async def add_citation(self, citation: Citation) -> None:
        try:
            self._connection.execute(
                "INSERT INTO citation (id, content_block_id, quote, locator) "
                "VALUES (?, ?, ?, ?)",
                (
                    _id(citation.id), _id(citation.content_block_id), citation.quote,
                    _json(citation.locator),
                ),
            )
        except sqlite3.IntegrityError as error:
            raise DomainValidationError("citation content block does not exist") from error

    async def add_claim(self, claim: Claim) -> None:
        try:
            self._connection.execute(
                """INSERT INTO claim
                   (id, project_id, subject_id, statement, confidence, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    _id(claim.id),
                    _id(claim.project_id),
                    _id(claim.subject_id),
                    claim.statement,
                    claim.confidence,
                    claim.status.value,
                    _timestamp(claim.created_at),
                ),
            )
            self._connection.executemany(
                "INSERT INTO claim_citation (claim_id, citation_id) VALUES (?, ?)",
                [(_id(claim.id), _id(citation.id)) for citation in claim.citations],
            )
        except sqlite3.IntegrityError as error:
            raise DomainValidationError(
                "claim project, subject, or citation does not exist"
            ) from error

    async def add_relation(self, relation: Relation) -> None:
        try:
            self._connection.execute(
                """INSERT INTO relation
                   (id, project_id, relation_type, source_id, target_id, properties,
                    confidence, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    _id(relation.id),
                    _id(relation.project_id),
                    relation.relation_type,
                    _id(relation.source_id),
                    _id(relation.target_id),
                    _json(relation.properties),
                    relation.confidence,
                    _timestamp(relation.created_at),
                ),
            )
            self._connection.executemany(
                "INSERT INTO relation_citation (relation_id, citation_id) VALUES (?, ?)",
                [(_id(relation.id), _id(citation_id)) for citation_id in relation.citation_ids],
            )
        except sqlite3.IntegrityError as error:
            raise DomainValidationError(
                "relation type, endpoints, project, or citation does not exist"
            ) from error

    async def add_relation_type(self, relation_type: RelationType) -> None:
        try:
            self._connection.execute(
                """INSERT INTO relation_type
                   (key, label, description, directional, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    relation_type.key,
                    relation_type.label,
                    relation_type.description,
                    int(relation_type.directional),
                    _timestamp(datetime.now(UTC)),
                ),
            )
        except sqlite3.IntegrityError as error:
            raise DomainValidationError("relation type key already exists") from error


class SQLiteJobRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    async def add(self, job: Job) -> None:
        try:
            self._connection.execute(
                """INSERT INTO job
                   (id, kind, idempotency_key, payload, status, progress, stage, attempt,
                    max_attempts, timeout_seconds, failure_reason, next_attempt_at,
                    created_at, started_at, finished_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                self._values(job),
            )
        except sqlite3.IntegrityError as error:
            raise DomainValidationError("job idempotency key already exists") from error

    async def save(self, job: Job) -> None:
        cursor = self._connection.execute(
            """UPDATE job SET kind = ?, idempotency_key = ?, payload = ?, status = ?,
               progress = ?, stage = ?, attempt = ?, max_attempts = ?, timeout_seconds = ?,
               failure_reason = ?, next_attempt_at = ?, created_at = ?, started_at = ?,
               finished_at = ? WHERE id = ?""",
            (*self._values(job)[1:], _id(job.id)),
        )
        if cursor.rowcount != 1:
            raise DomainValidationError("job does not exist")

    async def get(self, job_id: UUID) -> Job | None:
        row = self._connection.execute("SELECT * FROM job WHERE id = ?", (_id(job_id),)).fetchone()
        return self._from_row(row) if row is not None else None

    async def get_by_idempotency_key(self, key: str) -> Job | None:
        row = self._connection.execute(
            "SELECT * FROM job WHERE idempotency_key = ?", (key,)
        ).fetchone()
        return self._from_row(row) if row is not None else None

    async def list(self, *, limit: int = 100) -> list[Job]:
        rows = self._connection.execute(
            "SELECT * FROM job ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [self._from_row(row) for row in rows]

    @staticmethod
    def _values(job: Job) -> tuple[object, ...]:
        return (
            _id(job.id),
            job.kind,
            job.idempotency_key,
            _json(job.payload),
            job.status.value,
            job.progress,
            job.stage,
            job.attempt,
            job.max_attempts,
            job.timeout_seconds,
            job.failure_reason,
            _timestamp(job.next_attempt_at) if job.next_attempt_at else None,
            _timestamp(job.created_at),
            _timestamp(job.started_at) if job.started_at else None,
            _timestamp(job.finished_at) if job.finished_at else None,
        )

    @staticmethod
    def _from_row(row: sqlite3.Row) -> Job:
        return Job(
            kind=row["kind"],
            idempotency_key=row["idempotency_key"],
            payload=_mapping(row["payload"]),
            max_attempts=row["max_attempts"],
            timeout_seconds=row["timeout_seconds"],
            id=UUID(row["id"]),
            status=JobStatus(row["status"]),
            progress=row["progress"],
            stage=row["stage"],
            attempt=row["attempt"],
            failure_reason=row["failure_reason"],
            next_attempt_at=_datetime(row["next_attempt_at"]),
            created_at=_required_datetime(row["created_at"]),
            started_at=_datetime(row["started_at"]),
            finished_at=_datetime(row["finished_at"]),
        )


class SQLiteUnitOfWork:
    def __init__(self, store: SQLiteStore) -> None:
        self._connection = store.connect()
        self._connection.execute("BEGIN")
        self.sources: SourceRepository = SQLiteSourceRepository(self._connection)
        self.knowledge: KnowledgeRepository = SQLiteKnowledgeRepository(self._connection)
        self.jobs: JobRepository = SQLiteJobRepository(self._connection)
        self._committed = False

    async def __aenter__(self) -> SQLiteUnitOfWork:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if exc_type is not None or not self._committed:
            await self.rollback()
        self._connection.close()

    async def commit(self) -> None:
        self._connection.commit()
        self._committed = True

    async def rollback(self) -> None:
        self._connection.rollback()


class SQLiteUnitOfWorkFactory:
    def __init__(self, store: SQLiteStore) -> None:
        self.store = store

    def __call__(self) -> UnitOfWork:
        return SQLiteUnitOfWork(self.store)


class SQLiteJobQueue(JobQueue):
    """Durable queue view backed by jobs in SQLite.

    Enqueue is intentionally a no-op: the committed job row is the queue.
    This lets an API process and a separately started worker share work locally.
    """

    def __init__(self, store: SQLiteStore, poll_interval_seconds: float = 0.25) -> None:
        self._store = store
        self._poll_interval_seconds = poll_interval_seconds

    async def enqueue(self, job_id: UUID) -> None:
        return None

    async def dequeue(self, *, timeout_seconds: float | None = None) -> UUID | None:
        deadline = monotonic() + timeout_seconds if timeout_seconds is not None else None
        while True:
            connection = self._store.connect()
            try:
                row = connection.execute(
                    """SELECT id FROM job
                       WHERE status = 'queued'
                          OR (status = 'retrying' AND
                              (next_attempt_at IS NULL OR next_attempt_at <= ?))
                       ORDER BY created_at ASC LIMIT 1""",
                    (_timestamp(datetime.now(UTC)),),
                ).fetchone()
            finally:
                connection.close()
            if row is not None:
                return UUID(row["id"])
            if deadline is not None and monotonic() >= deadline:
                return None
            await asyncio.sleep(self._poll_interval_seconds)


__all__ = [
    "SQLiteJobQueue",
    "SQLiteStore",
    "SQLiteUnitOfWork",
    "SQLiteUnitOfWorkFactory",
]
