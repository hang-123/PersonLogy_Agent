"""SQLite-backed P8 retrieval and P10 schema-management features."""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from personlogy.application.audit import append_audit_event
from personlogy.application.lineage import add_lineage_link
from personlogy.domain.audit import digest_for
from personlogy.domain.schema.models import (
    SchemaChange,
    SchemaChangeKind,
    SchemaProposal,
    SchemaProposalStatus,
    SchemaSnapshot,
    as_definition,
)
from personlogy.ports.audit import AuditSink
from personlogy.ports.lineage import LineageStore
from personlogy.ports.retrieval import Evidence, RelationPath, RetrievalHit
from personlogy.ports.schema_management import SchemaRegistry
from personlogy.shared.errors import DomainValidationError
from personlogy.shared.trace import TraceContext

FEATURE_SCHEMA = """
CREATE TABLE IF NOT EXISTS retrieval_document (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES project(id),
    claim_id TEXT NOT NULL UNIQUE REFERENCES claim(id),
    content TEXT NOT NULL,
    index_version INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS retrieval_document_project_idx
    ON retrieval_document(project_id, index_version);
CREATE VIRTUAL TABLE IF NOT EXISTS retrieval_document_fts USING fts5(
    document_id UNINDEXED,
    project_id UNINDEXED,
    content
);
CREATE TABLE IF NOT EXISTS retrieval_index_build (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES project(id),
    version INTEGER NOT NULL,
    status TEXT NOT NULL,
    document_count INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(project_id, version)
);
CREATE TABLE IF NOT EXISTS schema_snapshot (
    id TEXT PRIMARY KEY,
    namespace TEXT NOT NULL,
    version INTEGER NOT NULL,
    checksum TEXT NOT NULL,
    definition TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(namespace, version),
    UNIQUE(namespace, checksum)
);
CREATE TABLE IF NOT EXISTS schema_proposal (
    id TEXT PRIMARY KEY,
    namespace TEXT NOT NULL,
    base_version INTEGER NOT NULL,
    target_version INTEGER NOT NULL,
    definition TEXT NOT NULL,
    changes TEXT NOT NULL,
    author TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    validated_at TEXT,
    applied_at TEXT
);
CREATE TABLE IF NOT EXISTS schema_audit (
    id TEXT PRIMARY KEY,
    proposal_id TEXT NOT NULL REFERENCES schema_proposal(id),
    action TEXT NOT NULL,
    details TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""

_ALLOWED_STATUSES = ("human_verified", "ready_for_writeback")
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class SQLiteFeatureStore:
    """Owns feature tables while sharing the application's SQLite database file."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        connection = self.connect()
        try:
            connection.executescript(FEATURE_SCHEMA)
        finally:
            connection.close()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection


class SQLiteRetrievalIndexer:
    def __init__(
        self,
        store: SQLiteFeatureStore,
        audit_sink: AuditSink | None = None,
        lineage_store: LineageStore | None = None,
    ) -> None:
        self._store = store
        self._audit_sink = audit_sink
        self._lineage_store = lineage_store

    async def rebuild_project(self, project_id: UUID, *, job_id: UUID | None = None) -> int:
        context = TraceContext.current_or_root().child()
        build_id = uuid4()
        entity_id = str(build_id)
        metadata = {"build_id": entity_id, "project_id": str(project_id)}
        await append_audit_event(
            self._audit_sink,
            event_type="index_build.started",
            status="started",
            entity_type="index_build",
            entity_id=entity_id,
            context=context,
            metadata=metadata,
        )
        connection = self._store.connect()
        version: int | None = None
        documents: list[tuple[str, str]] = []
        try:
            connection.execute("BEGIN")
            row = connection.execute(
                "SELECT COALESCE(MAX(version), 0) + 1 AS version "
                "FROM retrieval_index_build WHERE project_id = ?",
                (str(project_id),),
            ).fetchone()
            version = int(row["version"])
            connection.execute(
                "INSERT INTO retrieval_index_build "
                "(id, project_id, version, status, document_count, created_at) "
                "VALUES (?, ?, ?, 'running', 0, ?)",
                (str(build_id), str(project_id), version, _timestamp(datetime.now(UTC))),
            )
            old_documents = connection.execute(
                "SELECT id FROM retrieval_document WHERE project_id = ?", (str(project_id),)
            ).fetchall()
            connection.executemany(
                "DELETE FROM retrieval_document_fts WHERE document_id = ?",
                [(row["id"],) for row in old_documents],
            )
            connection.execute(
                "DELETE FROM retrieval_document WHERE project_id = ?", (str(project_id),)
            )

            claims = connection.execute(
                """SELECT c.id, c.statement, c.subject_id, n.title
                   FROM claim AS c
                   JOIN knowledge_node AS n ON n.id = c.subject_id
                   WHERE c.project_id = ? AND c.status IN (?, ?)
                   ORDER BY c.created_at ASC""",
                (str(project_id), *_ALLOWED_STATUSES),
            ).fetchall()
            for claim in claims:
                quotes = connection.execute(
                    """SELECT citation.quote FROM citation
                       JOIN claim_citation ON claim_citation.citation_id = citation.id
                       WHERE claim_citation.claim_id = ? ORDER BY citation.rowid""",
                    (claim["id"],),
                ).fetchall()
                content = " ".join(
                    [claim["title"], claim["statement"], *(item["quote"] for item in quotes)]
                )
                document_id = str(uuid4())
                connection.execute(
                    """INSERT INTO retrieval_document
                       (id, project_id, claim_id, content, index_version, created_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        document_id,
                        str(project_id),
                        claim["id"],
                        content,
                        version,
                        _timestamp(datetime.now(UTC)),
                    ),
                )
                documents.append((document_id, claim["id"]))
                connection.execute(
                    "INSERT INTO retrieval_document_fts(document_id, project_id, content) "
                    "VALUES (?, ?, ?)",
                    (document_id, str(project_id), content),
                )
            count = len(claims)
            connection.execute(
                "UPDATE retrieval_index_build SET status = 'succeeded', document_count = ? "
                "WHERE id = ?",
                (count, str(build_id)),
            )
            connection.commit()
            if job_id is not None:
                await add_lineage_link(
                    self._lineage_store,
                    project_id=project_id,
                    from_type="job",
                    from_id=job_id,
                    relation_type="produced",
                    to_type="index_build",
                    to_id=build_id,
                    metadata={"index_version": version},
                )
            for document_id, claim_id in documents:
                await add_lineage_link(
                    self._lineage_store,
                    project_id=project_id,
                    from_type="index_build",
                    from_id=build_id,
                    relation_type="contains",
                    to_type="retrieval_document",
                    to_id=document_id,
                    metadata={"index_version": version},
                )
                await add_lineage_link(
                    self._lineage_store,
                    project_id=project_id,
                    from_type="claim",
                    from_id=claim_id,
                    relation_type="indexed_as",
                    to_type="retrieval_document",
                    to_id=document_id,
                    metadata={"index_version": version},
                )
            await append_audit_event(
                self._audit_sink,
                event_type="index_build.succeeded",
                status="succeeded",
                entity_type="index_build",
                entity_id=entity_id,
                context=context,
                before={"status": "running", "version": version},
                after={"status": "succeeded", "version": version, "document_count": count},
                metadata={
                    **metadata,
                    "index_version": version,
                    "document_count": count,
                },
            )
            return count
        except Exception as error:
            connection.rollback()
            await append_audit_event(
                self._audit_sink,
                event_type="index_build.failed",
                status="failed",
                entity_type="index_build",
                entity_id=entity_id,
                context=context,
                before={"status": "running", "version": version or 0},
                after={"status": "failed", "version": version or 0},
                reason_code="index_build_failure",
                metadata={
                    **metadata,
                    "index_version": version or 0,
                    "error_digest": digest_for(str(error)),
                },
            )
            raise
        finally:
            connection.close()


class SQLiteRetrievalReader:
    def __init__(self, store: SQLiteFeatureStore) -> None:
        self._store = store

    async def search(
        self,
        *,
        project_id: UUID,
        query: str,
        limit: int = 20,
        expand_relations: bool = False,
    ) -> tuple[RetrievalHit, ...]:
        connection = self._store.connect()
        try:
            rows = self._search_rows(connection, project_id, query, limit)
            return tuple(
                self._hit_from_row(
                    connection,
                    row,
                    expand_relations=expand_relations,
                )
                for row in rows
            )
        finally:
            connection.close()

    @staticmethod
    def _search_rows(
        connection: sqlite3.Connection, project_id: UUID, query: str, limit: int
    ) -> list[sqlite3.Row]:
        phrase = '"' + query.replace('"', '""') + '"'
        try:
            rows = connection.execute(
                """SELECT d.claim_id, d.project_id, c.statement, c.subject_id, n.title,
                          bm25(retrieval_document_fts) AS rank
                   FROM retrieval_document_fts
                   JOIN retrieval_document AS d ON d.id = retrieval_document_fts.document_id
                   JOIN claim AS c ON c.id = d.claim_id
                   JOIN knowledge_node AS n ON n.id = c.subject_id
                   WHERE retrieval_document_fts.project_id = ?
                     AND retrieval_document_fts MATCH ?
                   ORDER BY rank ASC LIMIT ?""",
                (str(project_id), phrase, limit),
            ).fetchall()
        except sqlite3.OperationalError:
            rows = []
        if rows:
            return rows
        return connection.execute(
            """SELECT d.claim_id, d.project_id, c.statement, c.subject_id, n.title,
                      0.0 AS rank
               FROM retrieval_document AS d
               JOIN claim AS c ON c.id = d.claim_id
               JOIN knowledge_node AS n ON n.id = c.subject_id
               WHERE d.project_id = ? AND lower(d.content) LIKE lower(?)
               ORDER BY d.index_version DESC LIMIT ?""",
            (str(project_id), f"%{query}%", limit),
        ).fetchall()

    @classmethod
    def _hit_from_row(
        cls,
        connection: sqlite3.Connection,
        row: sqlite3.Row,
        *,
        expand_relations: bool,
    ) -> RetrievalHit:
        claim_id = UUID(row["claim_id"])
        subject_id = UUID(row["subject_id"])
        project_id = UUID(row["project_id"])
        evidence_rows = connection.execute(
            """SELECT c.id, c.quote, c.locator, s.id AS source_id, s.title AS source_title,
                      sv.id AS source_version_id
               FROM citation AS c
               JOIN claim_citation AS cc ON cc.citation_id = c.id
               JOIN content_block AS cb ON cb.id = c.content_block_id
               JOIN source_version AS sv ON sv.id = cb.source_version_id
               JOIN source AS s ON s.id = sv.source_id
               WHERE cc.claim_id = ? ORDER BY c.rowid""",
            (str(claim_id),),
        ).fetchall()
        evidence = tuple(
            Evidence(
                citation_id=UUID(item["id"]),
                quote=item["quote"],
                source_id=UUID(item["source_id"]),
                source_title=item["source_title"],
                source_version_id=UUID(item["source_version_id"]),
                locator=json.loads(item["locator"]),
            )
            for item in evidence_rows
        )
        relations = (
            cls._relations_for_subject(connection, project_id, subject_id)
            if expand_relations
            else ()
        )
        return RetrievalHit(
            claim_id=claim_id,
            project_id=project_id,
            statement=row["statement"],
            subject_id=subject_id,
            subject_title=row["title"],
            score=max(0.0, -float(row["rank"])),
            evidence=evidence,
            relations=relations,
        )

    @staticmethod
    def _relations_for_subject(
        connection: sqlite3.Connection, project_id: UUID, subject_id: UUID
    ) -> tuple[RelationPath, ...]:
        rows = connection.execute(
            """SELECT r.id, r.relation_type, r.source_id, r.target_id,
                      source_node.title AS source_title, target_node.title AS target_title
               FROM relation AS r
               JOIN knowledge_node AS source_node ON source_node.id = r.source_id
               JOIN knowledge_node AS target_node ON target_node.id = r.target_id
               WHERE r.project_id = ? AND r.status IN (?, ?)
                 AND (r.source_id = ? OR r.target_id = ?)
               ORDER BY r.created_at ASC""",
            (str(project_id), *_ALLOWED_STATUSES, str(subject_id), str(subject_id)),
        ).fetchall()
        return tuple(
            RelationPath(
                relation_id=UUID(item["id"]),
                relation_type=item["relation_type"],
                direction="outgoing" if item["source_id"] == str(subject_id) else "incoming",
                source_id=UUID(item["source_id"]),
                source_title=item["source_title"],
                target_id=UUID(item["target_id"]),
                target_title=item["target_title"],
            )
            for item in rows
        )


class SQLiteSchemaRegistry(SchemaRegistry):
    def __init__(self, store: SQLiteFeatureStore) -> None:
        self._store = store

    async def get_current_snapshot(self, namespace: str) -> SchemaSnapshot | None:
        connection = self._store.connect()
        try:
            row = connection.execute(
                "SELECT * FROM schema_snapshot WHERE namespace = ? "
                "ORDER BY version DESC LIMIT 1",
                (namespace,),
            ).fetchone()
            return _snapshot_from_row(row) if row else None
        finally:
            connection.close()

    async def save_snapshot(self, snapshot: SchemaSnapshot) -> None:
        connection = self._store.connect()
        try:
            connection.execute(
                "INSERT INTO schema_snapshot "
                "(id, namespace, version, checksum, definition, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    str(snapshot.id),
                    snapshot.namespace,
                    snapshot.version,
                    snapshot.checksum,
                    _json(snapshot.definition),
                    _timestamp(snapshot.created_at),
                ),
            )
            connection.commit()
        except sqlite3.IntegrityError as error:
            connection.rollback()
            raise DomainValidationError(
                "schema snapshot version or checksum already exists"
            ) from error
        finally:
            connection.close()

    async def save_proposal(self, proposal: SchemaProposal) -> None:
        connection = self._store.connect()
        try:
            connection.execute(
                """INSERT INTO schema_proposal
                   (id, namespace, base_version, target_version, definition, changes, author,
                    status, created_at, validated_at, applied_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET status = excluded.status,
                    definition = excluded.definition, changes = excluded.changes,
                    validated_at = excluded.validated_at, applied_at = excluded.applied_at""",
                (
                    str(proposal.id),
                    proposal.namespace,
                    proposal.base_version,
                    proposal.target_version,
                    _json(proposal.definition),
                    _json([_change_dict(change) for change in proposal.changes]),
                    proposal.author,
                    proposal.status.value,
                    _timestamp(proposal.created_at),
                    _timestamp(proposal.validated_at) if proposal.validated_at else None,
                    _timestamp(proposal.applied_at) if proposal.applied_at else None,
                ),
            )
            connection.commit()
        finally:
            connection.close()

    async def get_proposal(self, proposal_id: UUID) -> SchemaProposal | None:
        connection = self._store.connect()
        try:
            row = connection.execute(
                "SELECT * FROM schema_proposal WHERE id = ?", (str(proposal_id),)
            ).fetchone()
            return _proposal_from_row(row) if row else None
        finally:
            connection.close()


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _timestamp(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _snapshot_from_row(row: sqlite3.Row) -> SchemaSnapshot:
    return SchemaSnapshot(
        namespace=row["namespace"],
        version=row["version"],
        definition=as_definition(json.loads(row["definition"])),
        checksum=row["checksum"],
        id=UUID(row["id"]),
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def _change_dict(change: SchemaChange) -> dict[str, object]:
    return {
        "kind": change.kind.value,
        "path": change.path,
        "before": change.before,
        "after": change.after,
    }


def _proposal_from_row(row: sqlite3.Row) -> SchemaProposal:
    raw_changes = json.loads(row["changes"])
    if not isinstance(raw_changes, list):
        raise DomainValidationError("stored schema proposal changes are invalid")
    changes = tuple(
        SchemaChange(
            kind=SchemaChangeKind(item["kind"]),
            path=item["path"],
            before=item.get("before"),
            after=item.get("after"),
        )
        for item in raw_changes
    )
    return SchemaProposal(
        namespace=row["namespace"],
        base_version=row["base_version"],
        target_version=row["target_version"],
        definition=as_definition(json.loads(row["definition"])),
        changes=changes,
        author=row["author"],
        status=SchemaProposalStatus(row["status"]),
        id=UUID(row["id"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        validated_at=(
            datetime.fromisoformat(row["validated_at"]) if row["validated_at"] else None
        ),
        applied_at=datetime.fromisoformat(row["applied_at"]) if row["applied_at"] else None,
    )


__all__ = [
    "SQLiteFeatureStore",
    "SQLiteRetrievalIndexer",
    "SQLiteRetrievalReader",
    "SQLiteSchemaRegistry",
]
