import asyncio
from pathlib import Path

import pytest
from personlogy.adapters.sqlite_audit import SQLiteRecordStore
from personlogy.application.orchestration import (
    JOB_STAGE_COVERAGE,
    REQUIRED_STAGE_EVENTS,
    StageRunner,
    coverage_for,
)
from personlogy.domain.audit import AuditEvent
from personlogy.domain.job import Job
from personlogy.shared.trace import TraceContext


def test_stage_runner_records_success_and_child_span(tmp_path: Path) -> None:
    asyncio.run(_test_stage_runner_records_success_and_child_span(tmp_path))


async def _test_stage_runner_records_success_and_child_span(tmp_path: Path) -> None:
    audit = SQLiteRecordStore(tmp_path / "personlogy.sqlite3")
    runner = StageRunner(audit)
    job = Job("pdf.parse", "pdf:1", {}, trace_id="trace-stage", request_id="request-stage")
    parent = TraceContext.root(request_id="request-stage")

    with parent.activate():
        result = await runner.run(
            stage="pdf.parse",
            job=job,
            operation=_successful_operation,
        )

    assert result == "done"
    events = await audit.list(entity_id=f"{job.id}:0:pdf.parse")
    assert [event.event_type for event in events] == ["stage.started", "stage.succeeded"]
    assert events[0].trace_id == "trace-stage"
    assert events[0].parent_span_id == parent.span_id
    assert events[0].span_id == events[1].span_id
    assert events[1].metadata["duration_ms"] >= 0


async def _successful_operation() -> str:
    assert TraceContext.current() is not None
    return "done"


def test_stage_runner_records_failure_and_reraises(tmp_path: Path) -> None:
    asyncio.run(_test_stage_runner_records_failure_and_reraises(tmp_path))


async def _test_stage_runner_records_failure_and_reraises(tmp_path: Path) -> None:
    audit = SQLiteRecordStore(tmp_path / "personlogy.sqlite3")
    runner = StageRunner(audit)
    job = Job("knowledge.compile", "compile:1", {}, trace_id="trace-failure")

    with pytest.raises(RuntimeError, match="compile failed"):
        await runner.run(
            stage="knowledge.compile",
            job=job,
            operation=_failing_operation,
        )

    events = await audit.list(entity_id=f"{job.id}:0:knowledge.compile")
    assert [event.event_type for event in events] == ["stage.started", "stage.failed"]
    assert events[1].reason_code == "stage_failure"
    assert "error_digest" in events[1].metadata


async def _failing_operation() -> None:
    raise RuntimeError("compile failed")


def test_job_stage_coverage_matrix_matches_worker_stage_contract() -> None:
    assert {item.job_kind for item in JOB_STAGE_COVERAGE} == {
        "pdf.parse",
        "knowledge.compile",
        "retrieval.index",
    }
    for item in JOB_STAGE_COVERAGE:
        assert coverage_for(item.job_kind) == item
        assert item.required_events == REQUIRED_STAGE_EVENTS


class _FailingAuditSink:
    async def append(self, event: AuditEvent) -> AuditEvent:
        raise OSError(f"audit unavailable for {event.event_type}")


def test_stage_runner_does_not_execute_when_start_event_cannot_be_written() -> None:
    asyncio.run(_test_stage_runner_does_not_execute_when_start_event_cannot_be_written())


async def _test_stage_runner_does_not_execute_when_start_event_cannot_be_written() -> None:
    runner = StageRunner(_FailingAuditSink())
    job = Job("pdf.parse", "pdf:blocked", {}, trace_id="trace-blocked")
    called = False

    async def operation() -> None:
        nonlocal called
        called = True

    with pytest.raises(OSError, match="audit unavailable"):
        await runner.run(stage="pdf.parse", job=job, operation=operation)
    assert called is False
