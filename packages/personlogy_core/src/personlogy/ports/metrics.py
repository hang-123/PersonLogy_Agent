"""Ports for P10 event-derived metrics and operational health."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from personlogy.domain.metrics.models import MetricSnapshot, ProjectionFailure


class MetricsProjectionStore(Protocol):
    async def get_checkpoint(self) -> int: ...

    async def list_snapshots(
        self, *, metric_name: str | None = None, limit: int = 1000
    ) -> list[MetricSnapshot]: ...

    async def apply_batch(
        self,
        snapshots: Sequence[MetricSnapshot],
        *,
        checkpoint: int,
        captured_at: datetime,
    ) -> None: ...

    async def record_failure(self, *, sequence: int, error: str) -> ProjectionFailure: ...

    async def list_failures(
        self, *, unresolved_only: bool = True, limit: int = 100
    ) -> list[ProjectionFailure]: ...

    async def clear_failure(self, sequence: int) -> None: ...

    async def reset_projection(self) -> None: ...


@dataclass(frozen=True, slots=True)
class IndexHealth:
    latest_success_at: datetime | None
    latest_version: int | None
    age_seconds: float | None
    stale: bool


class OperationalProbe(Protocol):
    async def queue_backlog(self) -> int: ...

    async def index_health(
        self, *, now: datetime, stale_after_seconds: float
    ) -> IndexHealth: ...

    async def database_ready(self) -> bool: ...


__all__ = ["IndexHealth", "MetricsProjectionStore", "OperationalProbe"]
