"""SQLite persistence for non-destructive replay plans and comparisons."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import UUID

from personlogy.domain.replay import (
    ReplayComparison,
    ReplayPlan,
    ReplayPlanStatus,
    ReplayVersionSet,
)
from personlogy.shared.errors import DomainValidationError

REPLAY_SCHEMA = """
CREATE TABLE IF NOT EXISTS replay_plan (
    plan_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    source_version_id TEXT NOT NULL,
    parent_trace_id TEXT NOT NULL,
    parent_job_id TEXT,
    baseline_input_content_hash TEXT NOT NULL,
    baseline_schema_version TEXT,
    baseline_compiler_version TEXT NOT NULL,
    baseline_embedding_version TEXT,
    baseline_index_version INTEGER,
    target_input_content_hash TEXT NOT NULL,
    target_schema_version TEXT,
    target_compiler_version TEXT NOT NULL,
    target_embedding_version TEXT,
    target_index_version INTEGER,
    status TEXT NOT NULL,
    replay_job_id TEXT,
    created_at TEXT NOT NULL,
    approved_at TEXT
);
CREATE INDEX IF NOT EXISTS replay_plan_source_idx
    ON replay_plan(project_id, source_version_id, created_at);
CREATE TABLE IF NOT EXISTS replay_comparison (
    comparison_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    plan_id TEXT NOT NULL REFERENCES replay_plan(plan_id),
    source_version_id TEXT NOT NULL,
    replay_job_id TEXT NOT NULL,
    difference_dimensions TEXT NOT NULL,
    output_changed INTEGER,
    original_output_digest TEXT,
    replay_output_digest TEXT,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS replay_comparison_plan_idx
    ON replay_comparison(plan_id, created_at);
"""


def _optional_uuid(value: str | None) -> UUID | None:
    return UUID(value) if value else None


def _optional_datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _plan_from_row(row: sqlite3.Row) -> ReplayPlan:
    return ReplayPlan(
        plan_id=UUID(row["plan_id"]),
        project_id=UUID(row["project_id"]),
        source_version_id=UUID(row["source_version_id"]),
        parent_trace_id=row["parent_trace_id"],
        parent_job_id=_optional_uuid(row["parent_job_id"]),
        baseline_input_content_hash=row["baseline_input_content_hash"],
        baseline_versions=ReplayVersionSet(
            schema_version=row["baseline_schema_version"],
            compiler_version=row["baseline_compiler_version"],
            embedding_version=row["baseline_embedding_version"],
            index_version=row["baseline_index_version"],
        ),
        target_input_content_hash=row["target_input_content_hash"],
        target_versions=ReplayVersionSet(
            schema_version=row["target_schema_version"],
            compiler_version=row["target_compiler_version"],
            embedding_version=row["target_embedding_version"],
            index_version=row["target_index_version"],
        ),
        status=ReplayPlanStatus(row["status"]),
        replay_job_id=_optional_uuid(row["replay_job_id"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        approved_at=_optional_datetime(row["approved_at"]),
    )


def _comparison_from_row(row: sqlite3.Row) -> ReplayComparison:
    dimensions = json.loads(row["difference_dimensions"])
    if not isinstance(dimensions, list):
        raise ValueError("stored replay comparison dimensions are not a list")
    return ReplayComparison(
        comparison_id=UUID(row["comparison_id"]),
        project_id=UUID(row["project_id"]),
        plan_id=UUID(row["plan_id"]),
        source_version_id=UUID(row["source_version_id"]),
        replay_job_id=UUID(row["replay_job_id"]),
        difference_dimensions=tuple(cast(list[str], dimensions)),
        output_changed=(
            bool(row["output_changed"]) if row["output_changed"] is not None else None
        ),
        original_output_digest=row["original_output_digest"],
        replay_output_digest=row["replay_output_digest"],
        status=row["status"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )


class SQLiteReplayStore:
    """Append-safe local store for replay plans and candidate results."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        connection = self.connect()
        try:
            connection.executescript(REPLAY_SCHEMA)
        finally:
            connection.close()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    async def add_plan(self, plan: ReplayPlan) -> None:
        connection = self.connect()
        try:
            connection.execute(
                """INSERT INTO replay_plan (
                   plan_id, project_id, source_version_id, parent_trace_id, parent_job_id,
                   baseline_input_content_hash, baseline_schema_version,
                   baseline_compiler_version, baseline_embedding_version, baseline_index_version,
                   target_input_content_hash, target_schema_version, target_compiler_version,
                   target_embedding_version, target_index_version, status, replay_job_id,
                   created_at, approved_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                _plan_values(plan),
            )
            connection.commit()
        except sqlite3.IntegrityError as error:
            raise DomainValidationError("replay plan already exists") from error
        finally:
            connection.close()

    async def get_plan(self, plan_id: UUID) -> ReplayPlan | None:
        connection = self.connect()
        try:
            row = connection.execute(
                "SELECT * FROM replay_plan WHERE plan_id = ?", (str(plan_id),)
            ).fetchone()
            return _plan_from_row(row) if row is not None else None
        finally:
            connection.close()

    async def save_plan(self, plan: ReplayPlan) -> None:
        connection = self.connect()
        try:
            values = _plan_values(plan)
            cursor = connection.execute(
                """UPDATE replay_plan SET
                   project_id = ?, source_version_id = ?, parent_trace_id = ?,
                   parent_job_id = ?, baseline_input_content_hash = ?,
                   baseline_schema_version = ?, baseline_compiler_version = ?,
                   baseline_embedding_version = ?, baseline_index_version = ?,
                   target_input_content_hash = ?, target_schema_version = ?,
                   target_compiler_version = ?, target_embedding_version = ?,
                   target_index_version = ?, status = ?, replay_job_id = ?,
                   created_at = ?, approved_at = ?
                   WHERE plan_id = ?""",
                (*values[1:], values[0]),
            )
            if cursor.rowcount != 1:
                raise DomainValidationError("replay plan does not exist")
            connection.commit()
        finally:
            connection.close()

    async def add_comparison(self, comparison: ReplayComparison) -> None:
        connection = self.connect()
        try:
            connection.execute(
                """INSERT INTO replay_comparison (
                   comparison_id, project_id, plan_id, source_version_id, replay_job_id,
                   difference_dimensions, output_changed, original_output_digest,
                   replay_output_digest, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(comparison.comparison_id),
                    str(comparison.project_id),
                    str(comparison.plan_id),
                    str(comparison.source_version_id),
                    str(comparison.replay_job_id),
                    json.dumps(list(comparison.difference_dimensions), separators=(",", ":")),
                    (
                        int(comparison.output_changed)
                        if comparison.output_changed is not None
                        else None
                    ),
                    comparison.original_output_digest,
                    comparison.replay_output_digest,
                    comparison.status,
                    comparison.created_at.astimezone(UTC).isoformat(),
                ),
            )
            connection.commit()
        except sqlite3.IntegrityError as error:
            raise DomainValidationError("replay comparison already exists") from error
        finally:
            connection.close()

    async def get_comparison(self, comparison_id: UUID) -> ReplayComparison | None:
        connection = self.connect()
        try:
            row = connection.execute(
                "SELECT * FROM replay_comparison WHERE comparison_id = ?",
                (str(comparison_id),),
            ).fetchone()
            return _comparison_from_row(row) if row is not None else None
        finally:
            connection.close()

    async def list_comparisons(
        self, plan_id: UUID, *, limit: int = 100
    ) -> list[ReplayComparison]:
        if not 1 <= limit <= 1000:
            raise DomainValidationError("replay comparison limit must be between 1 and 1000")
        connection = self.connect()
        try:
            rows = connection.execute(
                "SELECT * FROM replay_comparison WHERE plan_id = ? "
                "ORDER BY created_at DESC LIMIT ?",
                (str(plan_id), limit),
            ).fetchall()
            return [_comparison_from_row(row) for row in rows]
        finally:
            connection.close()


def _plan_values(plan: ReplayPlan) -> tuple[object, ...]:
    return (
        str(plan.plan_id),
        str(plan.project_id),
        str(plan.source_version_id),
        plan.parent_trace_id,
        str(plan.parent_job_id) if plan.parent_job_id else None,
        plan.baseline_input_content_hash,
        plan.baseline_versions.schema_version,
        plan.baseline_versions.compiler_version,
        plan.baseline_versions.embedding_version,
        plan.baseline_versions.index_version,
        plan.target_input_content_hash,
        plan.target_versions.schema_version,
        plan.target_versions.compiler_version,
        plan.target_versions.embedding_version,
        plan.target_versions.index_version,
        plan.status.value,
        str(plan.replay_job_id) if plan.replay_job_id else None,
        plan.created_at.astimezone(UTC).isoformat(),
        plan.approved_at.astimezone(UTC).isoformat() if plan.approved_at else None,
    )


__all__ = ["REPLAY_SCHEMA", "SQLiteReplayStore"]
