import asyncio
import gzip
import shutil
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from personlogy.adapters.sqlite import SQLiteStore, SQLiteUnitOfWorkFactory
from personlogy.adapters.sqlite_audit import SQLiteRecordStore
from personlogy.adapters.sqlite_lineage import SQLiteLineageStore
from personlogy.adapters.telemetry import (
    OpenTelemetryMetricsExporter,
    OpenTelemetryTraceExporter,
    PrometheusMetricsExporter,
)
from personlogy.application.audit_operations import (
    archive_audit,
    export_audit,
    verify_audit_export,
)
from personlogy.application.backup_consistency import (
    SQLiteBackupConsistencyChecker,
    compare_sqlite_backups,
)
from personlogy.domain.audit import AuditEvent
from personlogy.domain.lineage import LineageLink
from personlogy.domain.metrics import MetricSnapshot
from personlogy.domain.source.models import Project, Source, SourceKind, SourceVersion
from personlogy.shared.trace import TraceContext


def _event(*, event_type: str = "job.succeeded") -> AuditEvent:
    return AuditEvent(
        event_type=event_type,
        status="succeeded",
        trace_id="trace-p10f",
        actor_type="system",
        entity_type="job",
        entity_id=str(uuid4()),
        occurred_at=datetime.now(UTC),
        metadata={"kind": "test"},
    )


def test_audit_export_archive_and_offline_verification(tmp_path: Path) -> None:
    asyncio.run(_test_audit_export_archive_and_offline_verification(tmp_path))


async def _test_audit_export_archive_and_offline_verification(tmp_path: Path) -> None:
    sink = SQLiteRecordStore(tmp_path / "audit.sqlite3")
    await sink.append(_event())
    await sink.append(_event(event_type="job.failed"))

    exported = await export_audit(sink, tmp_path / "audit.jsonl")
    verified = verify_audit_export(exported.path)
    assert exported.event_count == 2
    assert verified.chain.valid is True
    assert verified.chain.checked_events == 2

    archived = await archive_audit(sink, tmp_path / "audit.jsonl.gz")
    assert gzip.decompress(Path(archived.path).read_bytes()).count(b"\n") == 2
    assert verify_audit_export(archived.path).chain.valid is True

    tampered = tmp_path / "tampered.jsonl"
    tampered.write_bytes(Path(exported.path).read_bytes().replace(b"job.succeeded", b"job.changed"))
    assert verify_audit_export(tampered).chain.valid is False


def test_backup_restore_consistency_includes_audit_and_lineage(tmp_path: Path) -> None:
    asyncio.run(_test_backup_restore_consistency_includes_audit_and_lineage(tmp_path))


async def _test_backup_restore_consistency_includes_audit_and_lineage(tmp_path: Path) -> None:
    database = tmp_path / "source.sqlite3"
    store = SQLiteStore(database)
    audit = SQLiteRecordStore(database)
    lineage = SQLiteLineageStore(database)
    project = Project(name="P10-F", slug=f"p10f-{uuid4()}")
    source = Source(project.id, SourceKind.PDF, "backup")
    version = SourceVersion(source.id, 1, "content-hash", "object-key")
    async with SQLiteUnitOfWorkFactory(store)() as uow:
        await uow.sources.add_project(project)
        await uow.sources.add_source(source)
        await uow.sources.add_version(version)
        await uow.commit()
    await audit.append(_event())
    await lineage.add_link(
        LineageLink(
            project_id=project.id,
            from_type="source",
            from_id=str(source.id),
            relation_type="has_version",
            to_type="source_version",
            to_id=str(version.id),
        )
    )

    before = SQLiteBackupConsistencyChecker(database).report()
    assert before.valid is True
    restored = tmp_path / "restored.sqlite3"
    shutil.copy2(database, restored)
    comparison = compare_sqlite_backups(database, restored)
    assert comparison.identical is True
    assert comparison.differences == ()

    connection = SQLiteRecordStore(restored).connect()
    try:
        connection.execute("UPDATE audit_event SET status = 'failed' WHERE sequence = 1")
        connection.commit()
    finally:
        connection.close()
    after = SQLiteBackupConsistencyChecker(restored).report()
    assert after.valid is False
    assert after.audit_chain.valid is False


class _FakeSpan:
    def __init__(self, name: str, attributes: dict[str, object]) -> None:
        self.name = name
        self.attributes = attributes
        self.ended = False

    def end(self) -> None:
        self.ended = True


class _FakeTracer:
    def __init__(self) -> None:
        self.spans: list[_FakeSpan] = []

    def start_span(self, name: str, *, attributes: dict[str, object]) -> _FakeSpan:
        span = _FakeSpan(name, attributes)
        self.spans.append(span)
        return span


class _FakeInstrument:
    pass


class _FakeMeter:
    def __init__(self) -> None:
        self.callbacks: dict[str, object] = {}

    def create_observable_gauge(
        self, name: str, *, callbacks: list[object], description: str
    ) -> _FakeInstrument:
        self.callbacks[name] = callbacks[0]
        return _FakeInstrument()


def test_telemetry_bridges_preserve_p10_context_and_low_cardinality_metrics() -> None:
    tracer = _FakeTracer()
    context = TraceContext.root(request_id="request-p10f")
    event = _event()
    OpenTelemetryTraceExporter(tracer).export_event(event)
    assert len(tracer.spans) == 1
    assert tracer.spans[0].attributes["personlogy.trace_id"] == event.trace_id
    assert tracer.spans[0].ended is True

    snapshots = (
        MetricSnapshot("jobs.succeeded_total", 2, {"job_kind": "pdf.parse"}),
        MetricSnapshot("stages.duration_ms_last", 12.5, {"stage": "compile"}),
    )
    exposition = PrometheusMetricsExporter().render(snapshots)
    assert "personlogy_jobs_succeeded_total{job_kind=\"pdf.parse\"} 2" in exposition
    assert "# TYPE personlogy_jobs_succeeded_total counter" in exposition

    meter = _FakeMeter()
    exporter = OpenTelemetryMetricsExporter(meter)
    assert exporter.export(snapshots) == 2
    assert exporter.export(snapshots) == 2
    assert len(meter.callbacks) == 2

    with OpenTelemetryTraceExporter(tracer).span("p10f.test", context=context):
        pass
