"""Event-derived monitoring projection and operational health service."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

from personlogy.domain.audit import AuditEvent
from personlogy.domain.metrics import MetricSnapshot, ProjectionFailure
from personlogy.ports.audit import AuditSink, ChainVerification
from personlogy.ports.metrics import (
    IndexHealth,
    MetricsProjectionStore,
    OperationalProbe,
)

_JOB_COUNTERS = {
    "job.submitted": "jobs.submitted_total",
    "job.started": "jobs.started_total",
    "job.succeeded": "jobs.succeeded_total",
    "job.retrying": "jobs.retrying_total",
    "job.failed": "jobs.failed_total",
}
_UNKNOWN_TOOL_EVENTS = frozenset(
    {"auditor.review.failed", "tool.unknown", "tool.audit_degraded"}
)


@dataclass(frozen=True, slots=True)
class ProjectionRun:
    processed: int
    checkpoint: int
    failed_sequence: int | None = None


@dataclass(frozen=True, slots=True)
class MetricsView:
    checkpoint: int
    snapshots: tuple[MetricSnapshot, ...]
    failures: tuple[ProjectionFailure, ...]


@dataclass(frozen=True, slots=True)
class MonitoringHealth:
    status: str
    generated_at: datetime
    queue_backlog: int
    queue_degraded_threshold: int
    index: IndexHealth
    database_ready: bool
    audit_chain: ChainVerification
    projection_checkpoint: int
    projection_failures: tuple[ProjectionFailure, ...]
    job_failure_rate: float
    tool_unknown_state_total: float


class MetricsProjector:
    """Project ordered audit events into a restartable low-cardinality snapshot."""

    def __init__(
        self,
        audit_source: AuditSink,
        store: MetricsProjectionStore,
        *,
        batch_size: int = 500,
    ) -> None:
        if not 1 <= batch_size <= 5000:
            raise ValueError("metrics batch size must be between 1 and 5000")
        self._audit_source = audit_source
        self._store = store
        self._batch_size = batch_size

    async def run_once(self) -> ProjectionRun:
        checkpoint = await self._store.get_checkpoint()
        events = await self._audit_source.list_since(checkpoint, limit=self._batch_size)
        if not events:
            return ProjectionRun(processed=0, checkpoint=checkpoint)
        state = await self._state()
        for index, event in enumerate(events):
            sequence = event.sequence
            try:
                if sequence is None or sequence != checkpoint + 1 + index:
                    raise ValueError("audit sequence is not contiguous for metrics projection")
                self._project_event(state, event)
            except Exception as error:
                failed_sequence = sequence or checkpoint + 1
                await self._store.record_failure(sequence=failed_sequence, error=str(error))
                return ProjectionRun(
                    processed=max(0, failed_sequence - checkpoint - 1),
                    checkpoint=checkpoint,
                    failed_sequence=failed_sequence,
                )
        captured_at = datetime.now(UTC)
        await self._store.apply_batch(
            tuple(state.values()),
            checkpoint=events[-1].sequence or checkpoint,
            captured_at=captured_at,
        )
        return ProjectionRun(
            processed=len(events),
            checkpoint=events[-1].sequence or checkpoint,
        )

    async def run_until_caught_up(self, *, max_batches: int = 100) -> ProjectionRun:
        if not 1 <= max_batches <= 10000:
            raise ValueError("metrics max batches must be between 1 and 10000")
        processed = 0
        checkpoint = await self._store.get_checkpoint()
        for _ in range(max_batches):
            result = await self.run_once()
            processed += result.processed
            checkpoint = result.checkpoint
            if result.failed_sequence is not None or result.processed == 0:
                return ProjectionRun(
                    processed=processed,
                    checkpoint=checkpoint,
                    failed_sequence=result.failed_sequence,
                )
        return ProjectionRun(processed=processed, checkpoint=checkpoint)

    async def replay_failed(self) -> ProjectionRun:
        failures = await self._store.list_failures(unresolved_only=True, limit=1)
        if failures:
            await self._store.clear_failure(failures[0].sequence)
        return await self.run_until_caught_up()

    async def rebuild(self, *, max_batches: int = 10000) -> ProjectionRun:
        await self._store.reset_projection()
        return await self.run_until_caught_up(max_batches=max_batches)

    async def _state(self) -> dict[tuple[str, str], MetricSnapshot]:
        snapshots = await self._store.list_snapshots(limit=5000)
        return {
            (snapshot.metric_name, _tags_key(snapshot.tags)): snapshot
            for snapshot in snapshots
        }

    @staticmethod
    def _project_event(
        state: dict[tuple[str, str], MetricSnapshot], event: AuditEvent
    ) -> None:
        if event.event_type in _JOB_COUNTERS:
            metric_name = _JOB_COUNTERS[event.event_type]
            MetricsProjector._increment(state, metric_name, 1, {})
            MetricsProjector._increment(
                state,
                metric_name,
                1,
                {"job_kind": _tag_value(event.metadata, "kind")},
            )
        elif event.event_type in {"stage.succeeded", "stage.failed"}:
            stage = _tag_value(event.metadata, "stage")
            status = "succeeded" if event.event_type.endswith("succeeded") else "failed"
            MetricsProjector._increment(state, "stages.runs_total", 1, {"stage": stage})
            MetricsProjector._increment(
                state, f"stages.{status}_total", 1, {"stage": stage}
            )
            duration = _number(event.metadata.get("duration_ms"))
            if duration is not None:
                tags = {"stage": stage}
                MetricsProjector._increment(state, "stages.duration_ms_total", duration, tags)
                MetricsProjector._increment(state, "stages.duration_ms_count", 1, tags)
                MetricsProjector._set(state, "stages.duration_ms_last", duration, tags)
        elif event.event_type in {
            "retrieval.requested",
            "retrieval.succeeded",
            "retrieval.failed",
        }:
            MetricsProjector._increment(state, "retrieval.requests_total", 1, {})
            if event.event_type.endswith("succeeded"):
                MetricsProjector._increment(state, "retrieval.succeeded_total", 1, {})
            elif event.event_type.endswith("failed"):
                MetricsProjector._increment(state, "retrieval.failed_total", 1, {})
            duration = _number(event.metadata.get("duration_ms"))
            if duration is not None:
                MetricsProjector._increment(state, "retrieval.duration_ms_total", duration, {})
                MetricsProjector._increment(state, "retrieval.duration_ms_count", 1, {})
                MetricsProjector._set(state, "retrieval.duration_ms_last", duration, {})
            if event.event_type.endswith("succeeded"):
                result_count = _number(event.metadata.get("result_count"))
                if result_count is not None:
                    MetricsProjector._increment(
                        state, "retrieval.results_total", result_count, {}
                    )
        elif event.event_type in {
            "index_build.succeeded",
            "index_build.failed",
        }:
            status = "succeeded" if event.event_type.endswith("succeeded") else "failed"
            MetricsProjector._increment(state, f"index.build_{status}_total", 1, {})
            duration = _number(event.metadata.get("duration_ms"))
            if duration is not None:
                MetricsProjector._increment(state, "index.duration_ms_total", duration, {})
                MetricsProjector._increment(state, "index.duration_ms_count", 1, {})
        if event.event_type in _UNKNOWN_TOOL_EVENTS:
            MetricsProjector._increment(
                state,
                "tools.unknown_state_total",
                1,
                {"tool_name": _tag_value(event.metadata, "tool_name")},
            )

    @staticmethod
    def _increment(
        state: dict[tuple[str, str], MetricSnapshot],
        metric_name: str,
        amount: float,
        tags: Mapping[str, str],
    ) -> None:
        key = (metric_name, _tags_key(tags))
        existing = state.get(key)
        value = (existing.value if existing is not None else 0.0) + amount
        captured_at = datetime.now(UTC)
        state[key] = MetricSnapshot(
            metric_name=metric_name,
            value=value,
            tags=tags,
            captured_at=captured_at,
        )

    @staticmethod
    def _set(
        state: dict[tuple[str, str], MetricSnapshot],
        metric_name: str,
        value: float,
        tags: Mapping[str, str],
    ) -> None:
        state[(metric_name, _tags_key(tags))] = MetricSnapshot(
            metric_name=metric_name,
            value=value,
            tags=tags,
            captured_at=datetime.now(UTC),
        )


class MonitoringService:
    """Expose derived metrics and a bounded operational health summary."""

    def __init__(
        self,
        projector: MetricsProjector,
        store: MetricsProjectionStore,
        audit_sink: AuditSink,
        operational_probe: OperationalProbe,
        *,
        queue_degraded_threshold: int = 100,
        index_stale_after_seconds: float = 3600,
    ) -> None:
        self._projector = projector
        self._store = store
        self._audit_sink = audit_sink
        self._operational_probe = operational_probe
        self._queue_degraded_threshold = queue_degraded_threshold
        self._index_stale_after_seconds = index_stale_after_seconds

    async def metrics(self, *, metric_name: str | None = None, limit: int = 1000) -> MetricsView:
        await self._projector.run_until_caught_up()
        return MetricsView(
            checkpoint=await self._store.get_checkpoint(),
            snapshots=tuple(
                await self._store.list_snapshots(metric_name=metric_name, limit=limit)
            ),
            failures=tuple(await self._store.list_failures(unresolved_only=True)),
        )

    async def health(self) -> MonitoringHealth:
        await self._projector.run_until_caught_up()
        generated_at = datetime.now(UTC)
        snapshots = await self._store.list_snapshots(limit=5000)
        failures = tuple(await self._store.list_failures(unresolved_only=True))
        queue_backlog = await self._operational_probe.queue_backlog()
        index = await self._operational_probe.index_health(
            now=generated_at,
            stale_after_seconds=self._index_stale_after_seconds,
        )
        database_ready = await self._operational_probe.database_ready()
        audit_chain = await self._audit_sink.verify_chain()
        failure_rate = _failure_rate(snapshots)
        unknown_total = _snapshot_value(snapshots, "tools.unknown_state_total")
        degraded = (
            not database_ready
            or not audit_chain.valid
            or bool(failures)
            or queue_backlog > self._queue_degraded_threshold
            or index.stale
        )
        return MonitoringHealth(
            status="degraded" if degraded else "ok",
            generated_at=generated_at,
            queue_backlog=queue_backlog,
            queue_degraded_threshold=self._queue_degraded_threshold,
            index=index,
            database_ready=database_ready,
            audit_chain=audit_chain,
            projection_checkpoint=await self._store.get_checkpoint(),
            projection_failures=failures,
            job_failure_rate=failure_rate,
            tool_unknown_state_total=unknown_total,
        )


def _tags_key(tags: Mapping[str, str]) -> str:
    return json.dumps(dict(tags), sort_keys=True, separators=(",", ":"))


def _tag_value(metadata: Mapping[str, object], key: str) -> str:
    value = metadata.get(key)
    if isinstance(value, str) and value and len(value) <= 64:
        return value
    return "unknown"


def _number(value: object) -> float | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    numeric = float(value)
    return numeric if math.isfinite(numeric) and numeric >= 0 else None


def _snapshot_value(snapshots: list[MetricSnapshot], metric_name: str) -> float:
    return sum(snapshot.value for snapshot in snapshots if snapshot.metric_name == metric_name)


def _failure_rate(snapshots: list[MetricSnapshot]) -> float:
    failed = _snapshot_value(snapshots, "jobs.failed_total")
    succeeded = _snapshot_value(snapshots, "jobs.succeeded_total")
    denominator = succeeded + failed
    return failed / denominator if denominator else 0.0


__all__ = [
    "MetricsProjector",
    "MetricsView",
    "MonitoringHealth",
    "MonitoringService",
    "ProjectionRun",
]
