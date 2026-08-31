import asyncio
from pathlib import Path

import pytest
from personlogy.adapters.sqlite import SQLiteStore, SQLiteUnitOfWorkFactory
from personlogy.adapters.sqlite_audit import SQLiteRecordStore
from personlogy.adapters.sqlite_metrics import SQLiteMetricsStore
from personlogy.application.monitoring import MetricsProjector, MonitoringService
from personlogy.domain.audit import AuditEvent
from personlogy.domain.job import Job
from personlogy.domain.metrics import MetricSnapshot
from personlogy.shared.errors import DomainValidationError


def _event(
    event_type: str,
    *,
    sequence: int | None = None,
    metadata: dict[str, object] | None = None,
) -> AuditEvent:
    event = AuditEvent(
        event_type=event_type,
        status="succeeded",
        trace_id="trace-metrics",
        actor_type="system",
        entity_type="test",
        entity_id="test-1",
        metadata=metadata or {},
    )
    if sequence is None:
        return event
    return event.with_integrity(sequence=sequence, prev_hash=None, event_hash="0" * 64)


def test_metrics_projection_uses_checkpoint_and_rebuilds(tmp_path: Path) -> None:
    asyncio.run(_test_metrics_projection_uses_checkpoint_and_rebuilds(tmp_path))


async def _test_metrics_projection_uses_checkpoint_and_rebuilds(tmp_path: Path) -> None:
    database = tmp_path / "personlogy.sqlite3"
    audit = SQLiteRecordStore(database)
    metrics = SQLiteMetricsStore(database)
    await audit.append(
        AuditEvent(
            event_type="job.succeeded",
            status="succeeded",
            trace_id="trace-job",
            actor_type="system",
            entity_type="job",
            entity_id="job-1",
            metadata={"kind": "knowledge.compile"},
        )
    )
    await audit.append(
        AuditEvent(
            event_type="job.failed",
            status="failed",
            trace_id="trace-job",
            actor_type="system",
            entity_type="job",
            entity_id="job-2",
            metadata={"kind": "knowledge.compile"},
        )
    )
    await audit.append(
        AuditEvent(
            event_type="stage.succeeded",
            status="succeeded",
            trace_id="trace-stage",
            actor_type="system",
            entity_type="job_stage",
            entity_id="stage-1",
            metadata={"stage": "knowledge.compile", "duration_ms": 12.5},
        )
    )
    await audit.append(
        AuditEvent(
            event_type="auditor.review.failed",
            status="failed",
            trace_id="trace-tool",
            actor_type="system",
            entity_type="tool_invocation",
            entity_id="tool-1",
            metadata={"tool_name": "demo.write"},
        )
    )

    projector = MetricsProjector(audit, metrics, batch_size=2)
    first = await projector.run_until_caught_up()
    assert first.processed == 4
    assert await metrics.get_checkpoint() == 4
    assert (await projector.run_once()).processed == 0

    snapshots = await metrics.list_snapshots()
    values = {(item.metric_name, tuple(item.tags.items())): item.value for item in snapshots}
    assert values[("jobs.succeeded_total", ())] == 1
    assert values[("jobs.failed_total", ())] == 1
    assert values[("stages.duration_ms_last", (("stage", "knowledge.compile"),))] == 12.5
    assert values[("tools.unknown_state_total", (("tool_name", "demo.write"),))] == 1

    rebuilt = await projector.rebuild()
    assert rebuilt.processed == 4
    assert await metrics.get_checkpoint() == 4


class _MutableAuditSource:
    def __init__(self, events: list[AuditEvent]) -> None:
        self.events = events

    async def list_since(self, sequence: int, *, limit: int = 1000) -> list[AuditEvent]:
        return [event for event in self.events if (event.sequence or 0) > sequence][:limit]


def test_metrics_projection_records_and_replays_failure(tmp_path: Path) -> None:
    asyncio.run(_test_metrics_projection_records_and_replays_failure(tmp_path))


async def _test_metrics_projection_records_and_replays_failure(tmp_path: Path) -> None:
    metrics = SQLiteMetricsStore(tmp_path / "personlogy.sqlite3")
    valid = _event(
        "job.succeeded",
        sequence=1,
        metadata={"kind": "pdf.parse"},
    )
    invalid_sequence = _event(
        "job.succeeded",
        sequence=2,
        metadata={"kind": "pdf.parse"},
    )
    source = _MutableAuditSource([invalid_sequence])
    projector = MetricsProjector(source, metrics)

    failed = await projector.run_once()
    assert failed.failed_sequence == 2
    failures = await metrics.list_failures()
    assert failures[0].sequence == 2
    assert failures[0].error_digest

    source.events = [valid]
    replayed = await projector.replay_failed()
    assert replayed.processed == 1
    assert await metrics.get_checkpoint() == 1
    assert await metrics.list_failures() == []


def test_metric_snapshot_rejects_high_cardinality_or_sensitive_tags() -> None:
    with pytest.raises(DomainValidationError, match="tag name"):
        MetricSnapshot("jobs.failed_total", 1, {"trace_id": "trace-sensitive"})
    with pytest.raises(DomainValidationError, match="at most four"):
        MetricSnapshot(
            "jobs.failed_total",
            1,
            {"a": "1", "b": "2", "c": "3", "d": "4", "e": "5"},
        )


def test_monitoring_health_combines_projection_and_audit_state(tmp_path: Path) -> None:
    asyncio.run(_test_monitoring_health_combines_projection_and_audit_state(tmp_path))


async def _test_monitoring_health_combines_projection_and_audit_state(tmp_path: Path) -> None:
    database = tmp_path / "personlogy.sqlite3"
    store = SQLiteStore(database)
    audit = SQLiteRecordStore(database)
    metrics = SQLiteMetricsStore(database)
    async with SQLiteUnitOfWorkFactory(store)() as uow:
        await uow.jobs.add(Job("retrieval.index", "health-job", {}))
        await uow.commit()
    await audit.append(
        AuditEvent(
            event_type="job.failed",
            status="failed",
            trace_id="trace-health",
            actor_type="system",
            entity_type="job",
            entity_id="job-health",
            metadata={"kind": "retrieval.index"},
        )
    )
    monitoring = MonitoringService(
        MetricsProjector(audit, metrics),
        metrics,
        audit,
        metrics,
        queue_degraded_threshold=0,
    )

    health = await monitoring.health()
    assert health.status == "degraded"
    assert health.audit_chain.valid is True
    assert health.database_ready is True
    assert health.job_failure_rate == 1.0
    assert health.queue_backlog == 1
