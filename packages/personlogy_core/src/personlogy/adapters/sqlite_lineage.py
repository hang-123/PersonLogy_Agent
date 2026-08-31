"""SQLite append-only lineage storage and project-scoped graph traversal."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import UUID

from personlogy.domain.lineage import LineageLink
from personlogy.ports.lineage import LineageStore

LINEAGE_SCHEMA = """
CREATE TABLE IF NOT EXISTS lineage_link (
    link_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    from_type TEXT NOT NULL,
    from_id TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    to_type TEXT NOT NULL,
    to_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    metadata TEXT NOT NULL,
    UNIQUE(project_id, from_type, from_id, relation_type, to_type, to_id)
);
CREATE INDEX IF NOT EXISTS lineage_link_from_idx
    ON lineage_link(project_id, from_type, from_id, created_at);
CREATE INDEX IF NOT EXISTS lineage_link_to_idx
    ON lineage_link(project_id, to_type, to_id, created_at);
"""


def _metadata(value: str) -> dict[str, object]:
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("stored lineage metadata is not an object")
    return cast(dict[str, object], parsed)


def _link_from_row(row: sqlite3.Row) -> LineageLink:
    return LineageLink(
        link_id=UUID(row["link_id"]),
        project_id=UUID(row["project_id"]),
        from_type=row["from_type"],
        from_id=row["from_id"],
        relation_type=row["relation_type"],
        to_type=row["to_type"],
        to_id=row["to_id"],
        created_at=datetime.fromisoformat(row["created_at"]),
        metadata=_metadata(row["metadata"]),
    )


class SQLiteLineageStore(LineageStore):
    """Durable, idempotent lineage edges sharing the application database."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        connection = self.connect()
        try:
            connection.executescript(LINEAGE_SCHEMA)
        finally:
            connection.close()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    async def add_link(self, link: LineageLink) -> LineageLink:
        connection = self.connect()
        try:
            connection.execute(
                """INSERT INTO lineage_link
                   (link_id, project_id, from_type, from_id, relation_type, to_type, to_id,
                    created_at, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(project_id, from_type, from_id, relation_type, to_type, to_id)
                   DO NOTHING""",
                (
                    str(link.link_id),
                    str(link.project_id),
                    link.from_type,
                    link.from_id,
                    link.relation_type,
                    link.to_type,
                    link.to_id,
                    link.created_at.astimezone(UTC).isoformat(),
                    json.dumps(
                        dict(link.metadata),
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                ),
            )
            row = connection.execute(
                """SELECT * FROM lineage_link
                   WHERE project_id = ? AND from_type = ? AND from_id = ?
                     AND relation_type = ? AND to_type = ? AND to_id = ?""",
                (
                    str(link.project_id),
                    link.from_type,
                    link.from_id,
                    link.relation_type,
                    link.to_type,
                    link.to_id,
                ),
            ).fetchone()
            connection.commit()
            if row is None:  # pragma: no cover - protected by the insert/select transaction
                raise RuntimeError("lineage link was not persisted")
            return _link_from_row(row)
        finally:
            connection.close()

    async def trace_entity(
        self,
        *,
        project_id: UUID,
        entity_type: str,
        entity_id: str,
        limit: int = 1000,
    ) -> list[LineageLink]:
        if not entity_type.strip() or not entity_id.strip():
            raise ValueError("lineage entity type and ID are required")
        if not 1 <= limit <= 5000:
            raise ValueError("lineage query limit must be between 1 and 5000")
        connection = self.connect()
        try:
            rows = connection.execute(
                """WITH RECURSIVE reachable(entity_type, entity_id) AS (
                       SELECT ?, ?
                       UNION
                       SELECT l.to_type, l.to_id
                       FROM lineage_link AS l
                       JOIN reachable AS r
                         ON l.from_type = r.entity_type AND l.from_id = r.entity_id
                       WHERE l.project_id = ?
                       UNION
                       SELECT l.from_type, l.from_id
                       FROM lineage_link AS l
                       JOIN reachable AS r
                         ON l.to_type = r.entity_type AND l.to_id = r.entity_id
                       WHERE l.project_id = ?
                   )
                   SELECT l.* FROM lineage_link AS l
                   WHERE l.project_id = ?
                     AND (
                       EXISTS (
                           SELECT 1 FROM reachable AS r
                           WHERE r.entity_type = l.from_type AND r.entity_id = l.from_id
                       )
                       OR EXISTS (
                           SELECT 1 FROM reachable AS r
                           WHERE r.entity_type = l.to_type AND r.entity_id = l.to_id
                       )
                   )
                   ORDER BY l.created_at ASC, l.link_id ASC
                   LIMIT ?""",
                (
                    entity_type,
                    entity_id,
                    str(project_id),
                    str(project_id),
                    str(project_id),
                    limit,
                ),
            ).fetchall()
            return [_link_from_row(row) for row in rows]
        finally:
            connection.close()


__all__ = ["SQLiteLineageStore"]
