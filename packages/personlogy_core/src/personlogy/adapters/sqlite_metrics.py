"""SQLite projection and operational health adapters for P10-D."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import cast

from personlogy.domain.metrics import MetricSnapshot, ProjectionFailure
from personlogy.ports.metrics import (
    IndexHealth,
    MetricsProjectionStore,
    OperationalProbe,
)
from personlogy.shared.errors import DomainValidationError

METRICS_SCHEMA = """
CREATE TABLE IF NOT EXISTS metric_snapshot (
    metric_name TEXT NOT NULL,
    value REAL NOT NULL,
    tags TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    PRIMARY KEY(metric_name, tags)
);
CREATE TABLE IF NOT EXISTS metrics_projection_checkpoint (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    sequence INTEGER NOT NULL,
    updated_at TEXT NOT NULL
);
INSERT OR IGNORE INTO metrics_projection_checkpoint (id, sequence, updated_at)
VALUES (1, 0, '1970-01-01T00:00:00+00:00');
CREATE TABLE IF NOT EXISTS metrics_projection_failure (
    sequence INTEGER PRIMARY KEY,
    error_digest TEXT NOT NULL,
    attempts INTEGER NOT NULL,
    failed_at TEXT NOT NULL,
    resolved_at TEXT
);
"""


def _tags(value: str) -> dict[str, str]:
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise TypeError("stored metric tags are not an object")
    return cast(dict[str, str], parsed)


def _snapshot_from_row(row: sqlite3.Row) -> MetricSnapshot:
    return MetricSnapshot(
        metric_name=row["metric_name"],
        value=float(row["value"]),
        tags=_tags(row["tags"]),
        captured_at=datetime.fromisoformat(row["captured_at"]),
    )


def _failure_from_row(row: sqlite3.Row) -> ProjectionFailure:
    resolved_at = row["resolved_at"]
    return ProjectionFailure(
        sequence=int(row["sequence"]),
        error_digest=row["error_digest"],
        attempts=int(row["attempts"]),
        failed_at=datetime.fromisoformat(row["failed_at"]),
        resolved_at=datetime.fromisoformat(resolved_at) if resolved_at else None,
    )


class SQLiteMetricsStore(MetricsProjectionStore, OperationalProbe):
    """Persist low-frequency metric projections beside the local SQLite facts."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        connection = self.connect()
        try:
            connection.executescript(METRICS_SCHEMA)
        finally:
            connection.close()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    async def get_checkpoint(self) -> int:
        connection = self.connect()
        try:
            row = connection.execute(
                "SELECT sequence FROM metrics_projection_checkpoint WHERE id = 1"
            ).fetchone()
            if row is None:
                raise DomainValidationError("metrics projection checkpoint is missing")
            return int(row["sequence"])
        finally:
            connection.close()

    async def list_snapshots(
        self, *, metric_name: str | None = None, limit: int = 1000
    ) -> list[MetricSnapshot]:
        if not 1 <= limit <= 5000:
            raise DomainValidationError("metric query limit must be between 1 and 5000")
        connection = self.connect()
        try:
            if metric_name is None:
                rows = connection.execute(
                    "SELECT * FROM metric_snapshot ORDER BY metric_name, tags LIMIT ?",
                    (limit,),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM metric_snapshot WHERE metric_name = ? "
                    "ORDER BY tags LIMIT ?",
                    (metric_name, limit),
                ).fetchall()
            return [_snapshot_from_row(row) for row in rows]
        finally:
            connection.close()

    async def apply_batch(
        self,
        snapshots: Sequence[MetricSnapshot],
        *,
        checkpoint: int,
        captured_at: datetime,
    ) -> None:
        if checkpoint < 0:
            raise DomainValidationError("metrics checkpoint cannot be negative")
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            for snapshot in snapshots:
                connection.execute(
                    """INSERT INTO metric_snapshot (metric_name, value, tags, captured_at)
                       VALUES (?, ?, ?, ?)
                       ON CONFLICT(metric_name, tags) DO UPDATE SET
                       value = excluded.value, captured_at = excluded.captured_at""",
                    (
                        snapshot.metric_name,
                        snapshot.value,
                        json.dumps(
                            dict(snapshot.tags),
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                        snapshot.captured_at.astimezone(UTC).isoformat(),
                    ),
                )
            connection.execute(
                "UPDATE metrics_projection_checkpoint SET sequence = ?, updated_at = ? "
                "WHERE id = 1",
                (checkpoint, captured_at.astimezone(UTC).isoformat()),
            )
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    async def record_failure(self, *, sequence: int, error: str) -> ProjectionFailure:
        if sequence < 1:
            raise DomainValidationError("projection failure sequence must be positive")
        failed_at = datetime.now(UTC)
        error_digest = sha256(error.encode("utf-8")).hexdigest()
        connection = self.connect()
        try:
            connection.execute(
                """INSERT INTO metrics_projection_failure
                   (sequence, error_digest, attempts, failed_at, resolved_at)
                   VALUES (?, ?, 1, ?, NULL)
                   ON CONFLICT(sequence) DO UPDATE SET
                   error_digest = excluded.error_digest,
                   attempts = metrics_projection_failure.attempts + 1,
                   failed_at = excluded.failed_at,
                   resolved_at = NULL""",
                (sequence, error_digest, failed_at.isoformat()),
            )
            connection.commit()
            row = connection.execute(
                "SELECT * FROM metrics_projection_failure WHERE sequence = ?",
                (sequence,),
            ).fetchone()
            if row is None:  # pragma: no cover - guarded by the insert above
                raise DomainValidationError("projection failure was not persisted")
            return _failure_from_row(row)
        finally:
            connection.close()

    async def list_failures(
        self, *, unresolved_only: bool = True, limit: int = 100
    ) -> list[ProjectionFailure]:
        if not 1 <= limit <= 1000:
            raise DomainValidationError("projection failure limit must be between 1 and 1000")
        where = "WHERE resolved_at IS NULL" if unresolved_only else ""
        connection = self.connect()
        try:
            rows = connection.execute(
                f"SELECT * FROM metrics_projection_failure {where} "
                "ORDER BY sequence ASC LIMIT ?",
                (limit,),
            ).fetchall()
            return [_failure_from_row(row) for row in rows]
        finally:
            connection.close()

    async def clear_failure(self, sequence: int) -> None:
        connection = self.connect()
        try:
            connection.execute(
                "UPDATE metrics_projection_failure SET resolved_at = ? WHERE sequence = ?",
                (datetime.now(UTC).isoformat(), sequence),
            )
            connection.commit()
        finally:
            connection.close()

    async def reset_projection(self) -> None:
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("DELETE FROM metric_snapshot")
            connection.execute("DELETE FROM metrics_projection_failure")
            connection.execute(
                "UPDATE metrics_projection_checkpoint SET sequence = 0, updated_at = ? "
                "WHERE id = 1",
                (datetime.now(UTC).isoformat(),),
            )
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    async def queue_backlog(self) -> int:
        connection = self.connect()
        try:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM job WHERE status IN ('queued', 'retrying')"
            ).fetchone()
            return int(row["count"]) if row is not None else 0
        except sqlite3.OperationalError:
            return 0
        finally:
            connection.close()

    async def index_health(
        self, *, now: datetime, stale_after_seconds: float
    ) -> IndexHealth:
        if stale_after_seconds < 0:
            raise DomainValidationError("index stale threshold cannot be negative")
        connection = self.connect()
        try:
            row = connection.execute(
                "SELECT version, created_at FROM retrieval_index_build "
                "WHERE status = 'succeeded' ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
        except sqlite3.OperationalError:
            row = None
        finally:
            connection.close()
        if row is None:
            return IndexHealth(None, None, None, False)
        latest = datetime.fromisoformat(row["created_at"])
        age_seconds = max(0.0, (now - latest).total_seconds())
        return IndexHealth(
            latest_success_at=latest,
            latest_version=int(row["version"]),
            age_seconds=age_seconds,
            stale=age_seconds > stale_after_seconds,
        )

    async def database_ready(self) -> bool:
        connection = self.connect()
        try:
            connection.execute("SELECT 1").fetchone()
            return True
        except sqlite3.Error:
            return False
        finally:
            connection.close()


__all__ = ["METRICS_SCHEMA", "SQLiteMetricsStore"]
