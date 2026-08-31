"""Read-only audit and lineage consistency checks for SQLite backups."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from personlogy.adapters.sqlite_audit import _event_from_row
from personlogy.ports.audit import ChainVerification

_EXPECTED_TABLES = (
    "project",
    "source",
    "source_version",
    "content_block",
    "knowledge_node",
    "citation",
    "claim",
    "relation",
    "governance_run",
    "governance_issue",
    "duplicate_group",
    "conflict_record",
    "review_task",
    "job",
    "retrieval_document",
    "retrieval_index_build",
    "schema_snapshot",
    "schema_proposal",
    "schema_audit",
    "replay_plan",
    "replay_comparison",
    "audit_event",
    "audit_chain_head",
    "lineage_link",
)

_REQUIRED_TABLES = frozenset(
    {
        "project",
        "source",
        "source_version",
        "content_block",
        "audit_event",
        "audit_chain_head",
        "lineage_link",
    }
)

_ENTITY_PROJECT_SQL = {
    "source": "SELECT project_id FROM source WHERE id = ?",
    "source_version": (
        "SELECT s.project_id FROM source_version AS v "
        "JOIN source AS s ON s.id = v.source_id WHERE v.id = ?"
    ),
    "content_block": (
        "SELECT s.project_id FROM content_block AS b "
        "JOIN source_version AS v ON v.id = b.source_version_id "
        "JOIN source AS s ON s.id = v.source_id WHERE b.id = ?"
    ),
    "citation": (
        "SELECT s.project_id FROM citation AS c "
        "JOIN content_block AS b ON b.id = c.content_block_id "
        "JOIN source_version AS v ON v.id = b.source_version_id "
        "JOIN source AS s ON s.id = v.source_id WHERE c.id = ?"
    ),
    "node": "SELECT project_id FROM knowledge_node WHERE id = ?",
    "claim": "SELECT project_id FROM claim WHERE id = ?",
    "relation": "SELECT project_id FROM relation WHERE id = ?",
    "governance_run": "SELECT project_id FROM governance_run WHERE id = ?",
    "governance_issue": (
        "SELECT r.project_id FROM governance_issue AS i "
        "JOIN governance_run AS r ON r.id = i.run_id WHERE i.id = ?"
    ),
    "duplicate_group": "SELECT project_id FROM duplicate_group WHERE id = ?",
    "conflict_record": "SELECT project_id FROM conflict_record WHERE id = ?",
    "review_task": (
        "SELECT r.project_id FROM review_task AS t "
        "JOIN governance_run AS r ON r.id = t.run_id WHERE t.id = ?"
    ),
    "retrieval_document": "SELECT project_id FROM retrieval_document WHERE id = ?",
    "retrieval_index_build": "SELECT project_id FROM retrieval_index_build WHERE id = ?",
    "replay_plan": "SELECT project_id FROM replay_plan WHERE plan_id = ?",
    "replay_comparison": "SELECT project_id FROM replay_comparison WHERE comparison_id = ?",
}


@dataclass(frozen=True, slots=True)
class SQLiteConsistencyReport:
    path: str
    valid: bool
    issues: tuple[str, ...]
    table_counts: dict[str, int]
    audit_chain: ChainVerification
    lineage_count: int
    lineage_fingerprint: str
    fingerprint: str


@dataclass(frozen=True, slots=True)
class BackupRestoreComparison:
    before: SQLiteConsistencyReport
    after: SQLiteConsistencyReport
    identical: bool
    differences: tuple[str, ...]


class SQLiteBackupConsistencyChecker:
    """Generate a non-mutating consistency report from a SQLite database file."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)

    def _connect_readonly(self) -> sqlite3.Connection:
        if self.path == ":memory:":
            return sqlite3.connect(self.path)
        resolved = Path(self.path).resolve().as_posix()
        return sqlite3.connect(f"file:{resolved}?mode=ro", uri=True)

    def report(self) -> SQLiteConsistencyReport:
        connection = self._connect_readonly()
        connection.row_factory = sqlite3.Row
        issues: list[str] = []
        try:
            tables = {
                row["name"]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
            counts: dict[str, int] = {}
            for table in _EXPECTED_TABLES:
                if table not in tables:
                    counts[table] = 0
                    if table in _REQUIRED_TABLES:
                        issues.append(f"required table is missing: {table}")
                else:
                    counts[table] = int(
                        connection.execute(f"SELECT COUNT(*) FROM [{table}]").fetchone()[0]
                    )

            audit_chain = self._audit_chain(connection, tables, issues)
            lineage_count, lineage_digest = self._lineage(
                connection, tables, issues
            )
            table_material = json.dumps(
                counts, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            )
            material = f"{table_material}|{audit_chain}|{lineage_digest}"
            fingerprint = hashlib.sha256(material.encode("utf-8")).hexdigest()
            return SQLiteConsistencyReport(
                path=self.path,
                valid=not issues and audit_chain.valid,
                issues=tuple(issues),
                table_counts=counts,
                audit_chain=audit_chain,
                lineage_count=lineage_count,
                lineage_fingerprint=lineage_digest,
                fingerprint=fingerprint,
            )
        finally:
            connection.close()

    @staticmethod
    def _audit_chain(
        connection: sqlite3.Connection,
        tables: set[str],
        issues: list[str],
    ) -> ChainVerification:
        if "audit_event" not in tables or "audit_chain_head" not in tables:
            issues.append("audit chain tables are incomplete")
            return ChainVerification(False, 0, "audit chain tables are incomplete")
        rows = connection.execute("SELECT * FROM audit_event ORDER BY sequence ASC").fetchall()
        previous_hash: str | None = None
        for expected, row in enumerate(rows, start=1):
            try:
                event = _event_from_row(row)
            except (KeyError, TypeError, ValueError) as error:
                return ChainVerification(False, expected - 1, f"audit row is invalid: {error}")
            if event.sequence != expected:
                return ChainVerification(False, expected - 1, "audit sequence is not contiguous")
            if event.prev_hash != previous_hash:
                return ChainVerification(False, expected - 1, "audit previous hash does not match")
            if event.event_hash != event.hash_for(expected, previous_hash):
                return ChainVerification(False, expected - 1, "audit event hash does not match")
            previous_hash = event.event_hash
        head = connection.execute(
            "SELECT sequence, event_hash FROM audit_chain_head WHERE id = 1"
        ).fetchone()
        if (
            head is None
            or int(head["sequence"]) != len(rows)
            or head["event_hash"] != previous_hash
        ):
            return ChainVerification(
                False, len(rows), "audit chain head does not match events"
            )
        return ChainVerification(True, len(rows))

    @staticmethod
    def _lineage(
        connection: sqlite3.Connection,
        tables: set[str],
        issues: list[str],
    ) -> tuple[int, str]:
        if "lineage_link" not in tables:
            issues.append("required table is missing: lineage_link")
            return 0, ""
        rows = connection.execute(
            """SELECT project_id, from_type, from_id, relation_type, to_type, to_id,
                      created_at, metadata
               FROM lineage_link ORDER BY project_id, link_id"""
        ).fetchall()
        seen: set[tuple[object, ...]] = set()
        material: list[dict[str, object]] = []
        for row in rows:
            key = (
                row["project_id"], row["from_type"], row["from_id"],
                row["relation_type"], row["to_type"], row["to_id"],
            )
            if key in seen:
                issues.append("lineage contains duplicate logical links")
            seen.add(key)
            material.append(
                {
                    "project_id": row["project_id"],
                    "from_type": row["from_type"],
                    "from_id": row["from_id"],
                    "relation_type": row["relation_type"],
                    "to_type": row["to_type"],
                    "to_id": row["to_id"],
                    "created_at": row["created_at"],
                    "metadata": row["metadata"],
                }
            )
            for endpoint_type, endpoint_id in (
                (row["from_type"], row["from_id"]),
                (row["to_type"], row["to_id"]),
            ):
                query = _ENTITY_PROJECT_SQL.get(endpoint_type)
                if query is None or endpoint_type == "job":
                    # Some P10 entities are ephemeral (retrieval_request) or
                    # carry ownership in a payload (job); lineage still records them.
                    continue
                if endpoint_type == "node":
                    required_table = "knowledge_node"
                elif endpoint_type == "retrieval_index_build":
                    required_table = "retrieval_index_build"
                elif endpoint_type == "replay_plan":
                    required_table = "replay_plan"
                elif endpoint_type == "replay_comparison":
                    required_table = "replay_comparison"
                else:
                    required_table = endpoint_type
                if required_table not in tables:
                    issues.append(f"lineage endpoint table is missing: {required_table}")
                    continue
                owner = connection.execute(query, (endpoint_id,)).fetchone()
                if owner is None:
                    issues.append(f"lineage endpoint is missing: {endpoint_type}/{endpoint_id}")
                elif str(owner[0]) != str(row["project_id"]):
                    issues.append(
                        "lineage endpoint crosses project boundary: "
                        f"{endpoint_type}/{endpoint_id}"
                    )
        encoded = json.dumps(material, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return len(rows), hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def compare_sqlite_backups(
    before_path: str | Path, after_path: str | Path
) -> BackupRestoreComparison:
    """Compare pre-backup and post-restore integrity reports."""

    before = SQLiteBackupConsistencyChecker(before_path).report()
    after = SQLiteBackupConsistencyChecker(after_path).report()
    differences: list[str] = []
    if not before.valid:
        differences.append("pre-backup consistency report is invalid")
    if not after.valid:
        differences.append("post-restore consistency report is invalid")
    if before.table_counts != after.table_counts:
        differences.append("table row counts differ")
    if before.audit_chain != after.audit_chain:
        differences.append("audit chain verification differs")
    if before.lineage_count != after.lineage_count:
        differences.append("lineage row counts differ")
    if before.lineage_fingerprint != after.lineage_fingerprint:
        differences.append("lineage fingerprint differs")
    if before.fingerprint != after.fingerprint:
        differences.append("database consistency fingerprint differs")
    return BackupRestoreComparison(
        before=before,
        after=after,
        identical=not differences,
        differences=tuple(differences),
    )


__all__ = [
    "BackupRestoreComparison",
    "SQLiteBackupConsistencyChecker",
    "SQLiteConsistencyReport",
    "compare_sqlite_backups",
]
