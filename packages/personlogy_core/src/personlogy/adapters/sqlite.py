"""SQLite persistence adapters for local development and single-node execution."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from types import TracebackType
from typing import Self, cast
from uuid import UUID

from personlogy.domain.capture.models import (
    CaptureConflict,
    CapturedEvent,
    CaptureSourceIdentity,
    StreamState,
)
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
from personlogy.ports.capture import CaptureRepository
from personlogy.ports.queue import JobQueue
from personlogy.ports.repositories import (
    GovernanceRepository,
    JobRepository,
    KnowledgeRepository,
    SourceRepository,
)
from personlogy.ports.unit_of_work import UnitOfWork
from personlogy.ports.writeback import WritebackRepository
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
    locator TEXT NOT NULL,
    metadata TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS claim (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES project(id),
    subject_id TEXT NOT NULL REFERENCES knowledge_node(id),
    statement TEXT NOT NULL,
    confidence REAL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    metadata TEXT NOT NULL DEFAULT '{}'
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
    created_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'candidate',
    metadata TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS relation_citation (
    relation_id TEXT NOT NULL REFERENCES relation(id),
    citation_id TEXT NOT NULL REFERENCES citation(id),
    PRIMARY KEY(relation_id, citation_id)
);
CREATE TABLE IF NOT EXISTS governance_run (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES project(id),
    task_id TEXT NOT NULL,
    rule_version TEXT NOT NULL,
    status TEXT NOT NULL,
    candidate_ids TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS governance_issue (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES governance_run(id),
    candidate_id TEXT NOT NULL,
    candidate_kind TEXT NOT NULL,
    code TEXT NOT NULL,
    message TEXT NOT NULL,
    severity TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS duplicate_group (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES project(id),
    candidate_ids TEXT NOT NULL,
    basis TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS conflict_record (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES project(id),
    candidate_ids TEXT NOT NULL,
    basis TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);
    CREATE TABLE IF NOT EXISTS review_task (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES governance_run(id),
    candidate_id TEXT NOT NULL,
    candidate_kind TEXT NOT NULL,
    status TEXT NOT NULL,
    reviewer_id TEXT,
    reason TEXT,
    before TEXT NOT NULL,
    after TEXT NOT NULL,
    version INTEGER NOT NULL,
    created_at TEXT NOT NULL,
        reviewed_at TEXT
    );
    CREATE TABLE IF NOT EXISTS writeback_record (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL REFERENCES project(id),
        governance_run_id TEXT NOT NULL REFERENCES governance_run(id),
        schema_namespace TEXT NOT NULL,
        schema_version INTEGER NOT NULL,
        idempotency_key TEXT NOT NULL UNIQUE,
        request_digest TEXT NOT NULL,
        candidate_digest TEXT NOT NULL,
        candidates TEXT NOT NULL,
        status TEXT NOT NULL,
        effects_job_id TEXT,
        okf_object_key TEXT,
        index_job_id TEXT,
        error_code TEXT,
        error_digest TEXT,
        created_at TEXT NOT NULL,
        committed_at TEXT,
        completed_at TEXT
    );
    CREATE INDEX IF NOT EXISTS writeback_record_project_idx
        ON writeback_record(project_id, created_at);
    CREATE TABLE IF NOT EXISTS writeback_item (
        id TEXT PRIMARY KEY,
        record_id TEXT NOT NULL REFERENCES writeback_record(id),
        candidate_id TEXT NOT NULL,
        candidate_kind TEXT NOT NULL,
        before_status TEXT NOT NULL,
        after_status TEXT NOT NULL,
        before_digest TEXT NOT NULL,
        after_digest TEXT NOT NULL,
        result TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(record_id, candidate_id, candidate_kind)
    );
CREATE TABLE IF NOT EXISTS job (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    payload TEXT NOT NULL,
    trace_id TEXT NOT NULL DEFAULT '',
    request_id TEXT,
    span_id TEXT,
    parent_span_id TEXT,
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
CREATE TABLE IF NOT EXISTS capture_inbox_event (
    event_id TEXT PRIMARY KEY,
    producer_id TEXT NOT NULL,
    stream_id TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    source_kind TEXT NOT NULL,
    source_scope TEXT NOT NULL,
    session_key TEXT NOT NULL,
    source_item_key TEXT NOT NULL,
    source_revision INTEGER NOT NULL,
    occurred_at TEXT,
    captured_at TEXT NOT NULL,
    rule_version TEXT NOT NULL,
    schema_version INTEGER NOT NULL,
    payload_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(source_kind, source_scope, session_key, source_item_key, source_revision),
    UNIQUE(producer_id, stream_id, sequence)
);
CREATE INDEX IF NOT EXISTS capture_inbox_event_stream_idx
    ON capture_inbox_event(producer_id, stream_id, sequence);
CREATE TABLE IF NOT EXISTS capture_inbox_conflict (
    id TEXT PRIMARY KEY,
    source_kind TEXT NOT NULL,
    source_scope TEXT NOT NULL,
    session_key TEXT NOT NULL,
    source_item_key TEXT NOT NULL,
    source_revision INTEGER NOT NULL,
    existing_event_id TEXT NOT NULL,
    existing_payload_hash TEXT NOT NULL,
    incoming_event_id TEXT NOT NULL,
    incoming_payload_hash TEXT NOT NULL,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(source_kind, source_scope, session_key, source_item_key, source_revision,
           existing_event_id, incoming_event_id, reason)
);
CREATE TABLE IF NOT EXISTS capture_stream_state (
    producer_id TEXT NOT NULL,
    stream_id TEXT NOT NULL,
    next_sequence INTEGER NOT NULL DEFAULT 1,
    last_contiguous_received_sequence INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(producer_id, stream_id)
);
"""


def _json(value: dict[str, object]) -> str:
    return _json_value(value)


def _json_value(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def _mapping(value: str) -> dict[str, object]:
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise TypeError("stored JSON value is not an object")
    return cast(dict[str, object], parsed)


def _mappings(value: str) -> tuple[dict[str, object], ...]:
    parsed = json.loads(value)
    if not isinstance(parsed, list):
        raise TypeError("stored JSON value is not a list")
    return tuple(cast(dict[str, object], item) for item in parsed)


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


def _ensure_metadata_columns(connection: sqlite3.Connection) -> None:
    """Upgrade databases created before P5 metadata was introduced."""
    for table in ("citation", "claim", "relation"):
        columns = {
            row["name"] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if "metadata" not in columns:
            connection.execute(
                f"ALTER TABLE {table} ADD COLUMN metadata TEXT NOT NULL DEFAULT '{{}}'"
            )
        if table == "relation" and "status" not in columns:
            connection.execute(
                "ALTER TABLE relation ADD COLUMN status TEXT NOT NULL DEFAULT 'candidate'"
            )
    connection.commit()


def _ensure_job_trace_columns(connection: sqlite3.Connection) -> None:
    """Upgrade databases created before P10 trace context persistence."""
    columns = {row["name"] for row in connection.execute("PRAGMA table_info(job)").fetchall()}
    if "trace_id" not in columns:
        connection.execute("ALTER TABLE job ADD COLUMN trace_id TEXT NOT NULL DEFAULT ''")
    if "request_id" not in columns:
        connection.execute("ALTER TABLE job ADD COLUMN request_id TEXT")
    if "span_id" not in columns:
        connection.execute("ALTER TABLE job ADD COLUMN span_id TEXT")
    if "parent_span_id" not in columns:
        connection.execute("ALTER TABLE job ADD COLUMN parent_span_id TEXT")
    connection.execute(
        "UPDATE job SET trace_id = 'job:' || id WHERE trace_id IS NULL OR trace_id = ''"
    )
    connection.commit()


class SQLiteStore:
    """Database handle shared by UoW and queue instances."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._write_lock = asyncio.Lock()
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        connection = self.connect()
        try:
            connection.executescript(SCHEMA)
            _ensure_metadata_columns(connection)
            _ensure_job_trace_columns(connection)
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
        row = self._connection.execute("SELECT * FROM project WHERE slug = ?", (slug,)).fetchone()
        if row is None:
            return None
        return Project(
            name=row["name"],
            slug=row["slug"],
            id=UUID(row["id"]),
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

    async def get_source(self, project_id: UUID, kind: SourceKind, title: str) -> Source | None:
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
                    _id(conversation.id),
                    _id(conversation.project_id),
                    _id(conversation.source_id),
                    conversation.external_id,
                    conversation.title,
                    _json(conversation.metadata),
                    _timestamp(conversation.created_at),
                ),
            )
        except sqlite3.IntegrityError as error:
            raise DomainValidationError(
                "conversation project/source does not exist or id already exists"
            ) from error

    async def get_conversation(self, project_id: UUID, external_id: str) -> Conversation | None:
        row = self._connection.execute(
            """SELECT * FROM conversation
               WHERE project_id = ? AND external_id = ?""",
            (_id(project_id), external_id),
        ).fetchone()
        if row is None:
            return None
        return Conversation(
            project_id=UUID(row["project_id"]),
            source_id=UUID(row["source_id"]),
            external_id=row["external_id"],
            title=row["title"],
            metadata=_mapping(row["metadata"]),
            id=UUID(row["id"]),
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
                    _id(message.id),
                    _id(message.conversation_id),
                    message.external_id,
                    message.role,
                    message.content,
                    message.ordinal,
                    message.content_hash,
                    _timestamp(message.created_at),
                    message.parent_external_id,
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
            conversation_id=UUID(row["conversation_id"]),
            external_id=row["external_id"],
            role=row["role"],
            content=row["content"],
            ordinal=row["ordinal"],
            content_hash=row["content_hash"],
            created_at=_required_datetime(row["created_at"]),
            parent_external_id=row["parent_external_id"],
            attachments=_mappings(row["attachments"]),
            id=UUID(row["id"]),
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

    async def get_version_in_project(
        self, project_id: UUID, version_id: UUID
    ) -> SourceVersion | None:
        row = self._connection.execute(
            """SELECT version.* FROM source_version AS version
               JOIN source ON source.id = version.source_id
               WHERE version.id = ? AND source.project_id = ?""",
            (_id(version_id), _id(project_id)),
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

    async def get_block(self, block_id: UUID) -> ContentBlock | None:
        row = self._connection.execute(
            "SELECT * FROM content_block WHERE id = ?", (_id(block_id),)
        ).fetchone()
        if row is None:
            return None
        return ContentBlock(
            source_version_id=UUID(row["source_version_id"]),
            ordinal=row["ordinal"],
            content=row["content"],
            content_hash=row["content_hash"],
            locator=_mapping(row["locator"]),
            id=UUID(row["id"]),
        )

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

    async def get_node(self, node_id: UUID) -> KnowledgeNode | None:
        row = self._connection.execute(
            "SELECT * FROM knowledge_node WHERE id = ?", (_id(node_id),)
        ).fetchone()
        if row is None:
            return None
        return KnowledgeNode(
            project_id=UUID(row["project_id"]),
            node_type=row["node_type"],
            title=row["title"],
            properties=_mapping(row["properties"]),
            status=VerificationStatus(row["status"]),
            id=UUID(row["id"]),
            created_at=_required_datetime(row["created_at"]),
        )

    async def save_node(self, node: KnowledgeNode) -> None:
        cursor = self._connection.execute(
            "UPDATE knowledge_node SET properties = ?, status = ? WHERE id = ?",
            (_json(node.properties), node.status.value, _id(node.id)),
        )
        if cursor.rowcount != 1:
            raise DomainValidationError("knowledge node does not exist")

    async def add_citation(self, citation: Citation) -> None:
        try:
            self._connection.execute(
                "INSERT INTO citation (id, content_block_id, quote, locator, metadata) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    _id(citation.id),
                    _id(citation.content_block_id),
                    citation.quote,
                    _json(citation.locator),
                    _json(citation.metadata),
                ),
            )
        except sqlite3.IntegrityError as error:
            raise DomainValidationError("citation content block does not exist") from error

    async def get_citation(self, citation_id: UUID) -> Citation | None:
        row = self._connection.execute(
            "SELECT * FROM citation WHERE id = ?", (_id(citation_id),)
        ).fetchone()
        return _citation_from_row(row) if row is not None else None

    async def add_claim(self, claim: Claim) -> None:
        try:
            self._connection.execute(
                """INSERT INTO claim
                   (id, project_id, subject_id, statement, confidence, status, created_at, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    _id(claim.id),
                    _id(claim.project_id),
                    _id(claim.subject_id),
                    claim.statement,
                    claim.confidence,
                    claim.status.value,
                    _timestamp(claim.created_at),
                    _json(claim.metadata),
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

    async def get_claim(self, claim_id: UUID) -> Claim | None:
        row = self._connection.execute(
            "SELECT * FROM claim WHERE id = ?", (_id(claim_id),)
        ).fetchone()
        if row is None:
            return None
        citation_rows = self._connection.execute(
            """SELECT citation.* FROM citation
               JOIN claim_citation ON claim_citation.citation_id = citation.id
               WHERE claim_citation.claim_id = ? ORDER BY citation.rowid""",
            (_id(claim_id),),
        ).fetchall()
        citations = tuple(_citation_from_row(item) for item in citation_rows)
        return Claim(
            project_id=UUID(row["project_id"]),
            subject_id=UUID(row["subject_id"]),
            statement=row["statement"],
            citations=citations,
            confidence=row["confidence"],
            status=VerificationStatus(row["status"]),
            id=UUID(row["id"]),
            created_at=_required_datetime(row["created_at"]),
            metadata=_mapping(row["metadata"]),
        )

    async def save_claim(self, claim: Claim) -> None:
        cursor = self._connection.execute(
            "UPDATE claim SET status = ?, metadata = ? WHERE id = ?",
            (claim.status.value, _json(claim.metadata), _id(claim.id)),
        )
        if cursor.rowcount != 1:
            raise DomainValidationError("claim does not exist")

    async def add_relation(self, relation: Relation) -> None:
        try:
            self._connection.execute(
                """INSERT INTO relation
                   (id, project_id, relation_type, source_id, target_id, properties,
                    confidence, created_at, status, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    _id(relation.id),
                    _id(relation.project_id),
                    relation.relation_type,
                    _id(relation.source_id),
                    _id(relation.target_id),
                    _json(relation.properties),
                    relation.confidence,
                    _timestamp(relation.created_at),
                    relation.status.value,
                    _json(relation.metadata),
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

    async def get_relation(self, relation_id: UUID) -> Relation | None:
        row = self._connection.execute(
            "SELECT * FROM relation WHERE id = ?", (_id(relation_id),)
        ).fetchone()
        if row is None:
            return None
        citation_rows = self._connection.execute(
            "SELECT citation_id FROM relation_citation WHERE relation_id = ?",
            (_id(relation_id),),
        ).fetchall()
        return Relation(
            project_id=UUID(row["project_id"]),
            relation_type=row["relation_type"],
            source_id=UUID(row["source_id"]),
            target_id=UUID(row["target_id"]),
            citation_ids=tuple(UUID(item["citation_id"]) for item in citation_rows),
            properties=_mapping(row["properties"]),
            confidence=row["confidence"],
            id=UUID(row["id"]),
            created_at=_required_datetime(row["created_at"]),
            status=VerificationStatus(row["status"]),
            metadata=_mapping(row["metadata"]),
        )

    async def save_relation(self, relation: Relation) -> None:
        cursor = self._connection.execute(
            "UPDATE relation SET properties = ?, confidence = ?, status = ?, metadata = ? "
            "WHERE id = ?",
            (
                _json(relation.properties),
                relation.confidence,
                relation.status.value,
                _json(relation.metadata),
                _id(relation.id),
            ),
        )
        if cursor.rowcount != 1:
            raise DomainValidationError("relation does not exist")

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

    async def get_relation_type(self, key: str) -> RelationType | None:
        row = self._connection.execute(
            "SELECT key, label, description, directional FROM relation_type WHERE key = ?",
            (key,),
        ).fetchone()
        if row is None:
            return None
        return RelationType(
            key=row["key"],
            label=row["label"],
            description=row["description"],
            directional=bool(row["directional"]),
        )


class SQLiteGovernanceRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    async def add_run(self, run: GovernanceRun) -> None:
        try:
            self._connection.execute(
                """INSERT INTO governance_run
                   (id, project_id, task_id, rule_version, status, candidate_ids, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    _id(run.id),
                    _id(run.project_id),
                    _id(run.task_id),
                    run.rule_version,
                    run.status.value,
                    _json_value([str(item) for item in run.candidate_ids]),
                    _timestamp(run.created_at),
                ),
            )
        except sqlite3.IntegrityError as error:
            raise DomainValidationError("governance run project does not exist") from error

    async def add_issue(self, issue: GovernanceIssue) -> None:
        try:
            self._connection.execute(
                """INSERT INTO governance_issue
                   (id, run_id, candidate_id, candidate_kind, code, message, severity, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    _id(issue.id),
                    _id(issue.run_id),
                    _id(issue.candidate_id),
                    issue.candidate_kind.value,
                    issue.code,
                    issue.message,
                    issue.severity.value,
                    _timestamp(issue.created_at),
                ),
            )
        except sqlite3.IntegrityError as error:
            raise DomainValidationError("governance issue run does not exist") from error

    async def add_duplicate_group(self, group: DuplicateGroup) -> None:
        try:
            self._connection.execute(
                """INSERT INTO duplicate_group
                   (id, project_id, candidate_ids, basis, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    _id(group.id),
                    _id(group.project_id),
                    _json_value([str(item) for item in group.candidate_ids]),
                    group.basis,
                    _timestamp(group.created_at),
                ),
            )
        except sqlite3.IntegrityError as error:
            raise DomainValidationError("duplicate group project does not exist") from error

    async def add_conflict(self, conflict: ConflictRecord) -> None:
        try:
            self._connection.execute(
                """INSERT INTO conflict_record
                   (id, project_id, candidate_ids, basis, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    _id(conflict.id),
                    _id(conflict.project_id),
                    _json_value([str(item) for item in conflict.candidate_ids]),
                    conflict.basis,
                    conflict.status,
                    _timestamp(conflict.created_at),
                ),
            )
        except sqlite3.IntegrityError as error:
            raise DomainValidationError("conflict project does not exist") from error

    async def add_review_task(self, task: ReviewTask) -> None:
        try:
            self._connection.execute(
                """INSERT INTO review_task
                   (id, run_id, candidate_id, candidate_kind, status, reviewer_id, reason,
                    before, after, version, created_at, reviewed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    _id(task.id),
                    _id(task.run_id),
                    _id(task.candidate_id),
                    task.candidate_kind.value,
                    task.status.value,
                    task.reviewer_id,
                    task.reason,
                    _json(task.before),
                    _json(task.after),
                    task.version,
                    _timestamp(task.created_at),
                    _timestamp(task.reviewed_at) if task.reviewed_at else None,
                ),
            )
        except sqlite3.IntegrityError as error:
            raise DomainValidationError("review task governance run does not exist") from error

    async def get_review_task(self, task_id: UUID) -> ReviewTask | None:
        row = self._connection.execute(
            "SELECT * FROM review_task WHERE id = ?", (_id(task_id),)
        ).fetchone()
        return _review_task_from_row(row) if row is not None else None

    async def save_review_task(self, task: ReviewTask) -> None:
        cursor = self._connection.execute(
            """UPDATE review_task SET status = ?, reviewer_id = ?, reason = ?, before = ?,
               after = ?, version = ?, reviewed_at = ? WHERE id = ?""",
            (
                task.status.value,
                task.reviewer_id,
                task.reason,
                _json(task.before),
                _json(task.after),
                task.version,
                _timestamp(task.reviewed_at) if task.reviewed_at else None,
                _id(task.id),
            ),
        )
        if cursor.rowcount != 1:
            raise DomainValidationError("review task does not exist")

    async def list_review_tasks(
        self, *, limit: int = 100, project_id: UUID | None = None
    ) -> list[ReviewTask]:
        if project_id is None:
            rows = self._connection.execute(
                "SELECT * FROM review_task ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        else:
            rows = self._connection.execute(
                """SELECT review_task.* FROM review_task
                   JOIN governance_run ON governance_run.id = review_task.run_id
                   WHERE governance_run.project_id = ?
                   ORDER BY review_task.created_at DESC LIMIT ?""",
                (_id(project_id), limit),
            ).fetchall()
        return [_review_task_from_row(row) for row in rows]


class SQLiteWritebackRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    async def add(self, record: WritebackRecord) -> None:
        try:
            self._connection.execute(
                """INSERT INTO writeback_record
                   (id, project_id, governance_run_id, schema_namespace, schema_version,
                    idempotency_key, request_digest, candidate_digest, candidates, status,
                    effects_job_id, okf_object_key, index_job_id, error_code, error_digest,
                    created_at, committed_at, completed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    _id(record.id),
                    _id(record.project_id),
                    _id(record.governance_run_id),
                    record.schema_namespace,
                    record.schema_version,
                    record.idempotency_key,
                    record.request_digest,
                    record.candidate_digest,
                    _json_value(
                        [
                            {
                                "candidate_id": str(item.candidate_id),
                                "candidate_kind": item.candidate_kind.value,
                                "expected_review_version": item.expected_review_version,
                            }
                            for item in record.candidates
                        ]
                    ),
                    record.status.value,
                    _id(record.effects_job_id) if record.effects_job_id else None,
                    record.okf_object_key,
                    _id(record.index_job_id) if record.index_job_id else None,
                    record.error_code,
                    record.error_digest,
                    _timestamp(record.created_at),
                    _timestamp(record.committed_at) if record.committed_at else None,
                    _timestamp(record.completed_at) if record.completed_at else None,
                ),
            )
        except sqlite3.IntegrityError as error:
            raise DomainValidationError(
                "writeback idempotency key or parent already exists"
            ) from error

    async def get(self, record_id: UUID) -> WritebackRecord | None:
        row = self._connection.execute(
            "SELECT * FROM writeback_record WHERE id = ?", (_id(record_id),)
        ).fetchone()
        return _writeback_from_row(row) if row is not None else None

    async def get_by_idempotency_key(self, key: str) -> WritebackRecord | None:
        row = self._connection.execute(
            "SELECT * FROM writeback_record WHERE idempotency_key = ?", (key,)
        ).fetchone()
        return _writeback_from_row(row) if row is not None else None

    async def save(self, record: WritebackRecord) -> None:
        cursor = self._connection.execute(
            """UPDATE writeback_record SET status = ?, effects_job_id = ?, okf_object_key = ?,
               index_job_id = ?, error_code = ?, error_digest = ?, committed_at = ?,
               completed_at = ? WHERE id = ?""",
            (
                record.status.value,
                _id(record.effects_job_id) if record.effects_job_id else None,
                record.okf_object_key,
                _id(record.index_job_id) if record.index_job_id else None,
                record.error_code,
                record.error_digest,
                _timestamp(record.committed_at) if record.committed_at else None,
                _timestamp(record.completed_at) if record.completed_at else None,
                _id(record.id),
            ),
        )
        if cursor.rowcount != 1:
            raise DomainValidationError("writeback record does not exist")

    async def add_item(self, item: WritebackItem) -> None:
        try:
            self._connection.execute(
                """INSERT INTO writeback_item
                   (id, record_id, candidate_id, candidate_kind, before_status, after_status,
                    before_digest, after_digest, result, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    _id(item.id),
                    _id(item.record_id),
                    _id(item.candidate_id),
                    item.candidate_kind.value,
                    item.before_status.value,
                    item.after_status.value,
                    item.before_digest,
                    item.after_digest,
                    item.result,
                    _timestamp(item.created_at),
                ),
            )
        except sqlite3.IntegrityError as error:
            raise DomainValidationError(
                "writeback item record does not exist or already exists"
            ) from error

    async def list_items(self, record_id: UUID) -> list[WritebackItem]:
        rows = self._connection.execute(
            "SELECT * FROM writeback_item WHERE record_id = ? ORDER BY created_at ASC",
            (_id(record_id),),
        ).fetchall()
        return [_writeback_item_from_row(row) for row in rows]


def _review_task_from_row(row: sqlite3.Row) -> ReviewTask:
    return ReviewTask(
        run_id=UUID(row["run_id"]),
        candidate_id=UUID(row["candidate_id"]),
        candidate_kind=CandidateKind(row["candidate_kind"]),
        status=ReviewTaskStatus(row["status"]),
        reviewer_id=row["reviewer_id"],
        reason=row["reason"],
        before=_mapping(row["before"]),
        after=_mapping(row["after"]),
        version=row["version"],
        id=UUID(row["id"]),
        created_at=_required_datetime(row["created_at"]),
        reviewed_at=_datetime(row["reviewed_at"]),
    )


def _writeback_from_row(row: sqlite3.Row) -> WritebackRecord:
    return WritebackRecord(
        project_id=UUID(row["project_id"]),
        governance_run_id=UUID(row["governance_run_id"]),
        schema_namespace=row["schema_namespace"],
        schema_version=row["schema_version"],
        idempotency_key=row["idempotency_key"],
        request_digest=row["request_digest"],
        candidate_digest=row["candidate_digest"],
        candidates=_candidate_refs(row["candidates"]),
        status=WritebackStatus(row["status"]),
        effects_job_id=UUID(row["effects_job_id"]) if row["effects_job_id"] else None,
        okf_object_key=row["okf_object_key"],
        index_job_id=UUID(row["index_job_id"]) if row["index_job_id"] else None,
        error_code=row["error_code"],
        error_digest=row["error_digest"],
        id=UUID(row["id"]),
        created_at=_required_datetime(row["created_at"]),
        committed_at=_datetime(row["committed_at"]),
        completed_at=_datetime(row["completed_at"]),
    )


def _writeback_item_from_row(row: sqlite3.Row) -> WritebackItem:
    return WritebackItem(
        record_id=UUID(row["record_id"]),
        candidate_id=UUID(row["candidate_id"]),
        candidate_kind=CandidateKind(row["candidate_kind"]),
        before_status=VerificationStatus(row["before_status"]),
        after_status=VerificationStatus(row["after_status"]),
        before_digest=row["before_digest"],
        after_digest=row["after_digest"],
        result=row["result"],
        id=UUID(row["id"]),
        created_at=_required_datetime(row["created_at"]),
    )


def _citation_from_row(row: sqlite3.Row) -> Citation:
    return Citation(
        content_block_id=UUID(row["content_block_id"]),
        quote=row["quote"],
        locator=_mapping(row["locator"]),
        id=UUID(row["id"]),
        metadata=_mapping(row["metadata"]),
    )


class SQLiteJobRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    async def add(self, job: Job) -> None:
        try:
            self._connection.execute(
                """INSERT INTO job
                   (id, kind, idempotency_key, payload, trace_id, request_id, span_id,
                    parent_span_id, status, progress, stage, attempt,
                    max_attempts, timeout_seconds, failure_reason, next_attempt_at,
                    created_at, started_at, finished_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                self._values(job),
            )
        except sqlite3.IntegrityError as error:
            raise DomainValidationError("job idempotency key already exists") from error

    async def save(self, job: Job) -> None:
        cursor = self._connection.execute(
            """UPDATE job SET kind = ?, idempotency_key = ?, payload = ?, trace_id = ?,
               request_id = ?, span_id = ?, parent_span_id = ?, status = ?, progress = ?,
               stage = ?, attempt = ?, max_attempts = ?, timeout_seconds = ?,
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

    async def list(
        self,
        *,
        limit: int | None = 100,
        project_id: UUID | None = None,
        status: str | None = None,
    ) -> list[Job]:
        rows = self._connection.execute(
            """SELECT * FROM job
               WHERE (? IS NULL OR json_extract(payload, '$.project_id') = ?)
                 AND (? IS NULL OR status = ?)
               ORDER BY created_at DESC LIMIT ?""",
            (
                str(project_id) if project_id else None,
                str(project_id),
                status,
                status,
                limit if limit is not None else -1,
            ),
        ).fetchall()
        return [self._from_row(row) for row in rows]

    @staticmethod
    def _values(job: Job) -> tuple[object, ...]:
        return (
            _id(job.id),
            job.kind,
            job.idempotency_key,
            _json(job.payload),
            job.trace_id,
            job.request_id,
            job.span_id,
            job.parent_span_id,
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
            trace_id=row["trace_id"],
            request_id=row["request_id"],
            span_id=row["span_id"],
            parent_span_id=row["parent_span_id"],
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


class SQLiteCaptureRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    async def get_by_event_id(self, event_id: UUID) -> CapturedEvent | None:
        row = self._connection.execute(
            "SELECT * FROM capture_inbox_event WHERE event_id = ?", (_id(event_id),)
        ).fetchone()
        return _captured_event_from_row(row) if row is not None else None

    async def get_by_source_identity(
        self, identity: CaptureSourceIdentity
    ) -> CapturedEvent | None:
        row = self._connection.execute(
            """SELECT * FROM capture_inbox_event
               WHERE source_kind = ? AND source_scope = ? AND session_key = ?
                 AND source_item_key = ? AND source_revision = ?""",
            _source_identity_values(identity),
        ).fetchone()
        return _captured_event_from_row(row) if row is not None else None

    async def get_by_stream_sequence(
        self, producer_id: str, stream_id: str, sequence: int
    ) -> CapturedEvent | None:
        row = self._connection.execute(
            """SELECT * FROM capture_inbox_event
               WHERE producer_id = ? AND stream_id = ? AND sequence = ?""",
            (producer_id, stream_id, sequence),
        ).fetchone()
        return _captured_event_from_row(row) if row is not None else None

    async def add_event(self, event: CapturedEvent) -> None:
        try:
            self._connection.execute(
                """INSERT INTO capture_inbox_event (
                    event_id, producer_id, stream_id, sequence,
                    source_kind, source_scope, session_key, source_item_key,
                    source_revision, occurred_at, captured_at, rule_version,
                    schema_version, payload_hash, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    _id(event.event_id),
                    event.producer_id,
                    event.stream_id,
                    event.sequence,
                    *_source_identity_values(event.source_identity),
                    _timestamp(event.occurred_at) if event.occurred_at else None,
                    _timestamp(event.captured_at),
                    event.rule_version,
                    event.schema_version,
                    event.payload_hash.lower(),
                    _json(dict(event.payload)),
                    _timestamp(event.created_at),
                ),
            )
        except sqlite3.IntegrityError as error:
            raise DomainValidationError("capture event identity already exists") from error

    async def add_conflict(self, conflict: CaptureConflict) -> None:
        self._connection.execute(
            """INSERT OR IGNORE INTO capture_inbox_conflict (
                id, source_kind, source_scope, session_key, source_item_key,
                source_revision, existing_event_id, existing_payload_hash,
                incoming_event_id, incoming_payload_hash, reason, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                _id(conflict.id),
                *_source_identity_values(conflict.source_identity),
                _id(conflict.existing_event_id),
                conflict.existing_payload_hash,
                _id(conflict.incoming_event_id),
                conflict.incoming_payload_hash,
                conflict.reason,
                _timestamp(conflict.created_at),
            ),
        )

    async def get_stream_state(self, producer_id: str, stream_id: str) -> StreamState | None:
        row = self._connection.execute(
            """SELECT * FROM capture_stream_state
               WHERE producer_id = ? AND stream_id = ?""",
            (producer_id, stream_id),
        ).fetchone()
        if row is None:
            return None
        return StreamState(
            producer_id=row["producer_id"],
            stream_id=row["stream_id"],
            next_sequence=row["next_sequence"],
            last_contiguous_received_sequence=row["last_contiguous_received_sequence"],
            updated_at=_required_datetime(row["updated_at"]),
        )

    async def save_stream_state(self, state: StreamState) -> None:
        self._connection.execute(
            """INSERT INTO capture_stream_state (
                producer_id, stream_id, next_sequence,
                last_contiguous_received_sequence, updated_at
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(producer_id, stream_id) DO UPDATE SET
                next_sequence = excluded.next_sequence,
                last_contiguous_received_sequence = excluded.last_contiguous_received_sequence,
                updated_at = excluded.updated_at""",
            (
                state.producer_id,
                state.stream_id,
                state.next_sequence,
                state.last_contiguous_received_sequence,
                _timestamp(state.updated_at),
            ),
        )


def _source_identity_values(identity: CaptureSourceIdentity) -> tuple[object, ...]:
    return (
        identity.source_kind,
        identity.source_scope,
        identity.session_key,
        identity.source_item_key,
        identity.source_revision,
    )


def _captured_event_from_row(row: sqlite3.Row) -> CapturedEvent:
    return CapturedEvent(
        schema_version=row["schema_version"],
        event_id=UUID(row["event_id"]),
        producer_id=row["producer_id"],
        stream_id=row["stream_id"],
        sequence=row["sequence"],
        source_identity=CaptureSourceIdentity(
            source_kind=row["source_kind"],
            source_scope=row["source_scope"],
            session_key=row["session_key"],
            source_item_key=row["source_item_key"],
            source_revision=row["source_revision"],
        ),
        occurred_at=_datetime(row["occurred_at"]),
        captured_at=_required_datetime(row["captured_at"]),
        rule_version=row["rule_version"],
        payload_hash=row["payload_hash"],
        payload=_mapping(row["payload_json"]),
        created_at=_required_datetime(row["created_at"]),
    )


class SQLiteUnitOfWork:
    def __init__(self, store: SQLiteStore) -> None:
        self._store = store
        self._connection = store.connect()
        self._connection.execute("BEGIN")
        self.sources: SourceRepository = SQLiteSourceRepository(self._connection)
        self.knowledge: KnowledgeRepository = SQLiteKnowledgeRepository(self._connection)
        self.governance: GovernanceRepository = SQLiteGovernanceRepository(self._connection)
        self.writebacks: WritebackRepository = SQLiteWritebackRepository(self._connection)
        self.jobs: JobRepository = SQLiteJobRepository(self._connection)
        self.capture: CaptureRepository = SQLiteCaptureRepository(self._connection)
        self._committed = False

    async def __aenter__(self) -> Self:
        await self._store._write_lock.acquire()
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
        self._store._write_lock.release()

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
    "SQLiteCaptureRepository",
    "SQLiteJobQueue",
    "SQLiteStore",
    "SQLiteUnitOfWork",
    "SQLiteUnitOfWorkFactory",
    "SQLiteWritebackRepository",
]
