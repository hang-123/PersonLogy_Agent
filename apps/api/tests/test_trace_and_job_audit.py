import asyncio
from pathlib import Path

from personlogy.adapters.sqlite import SQLiteJobQueue, SQLiteStore, SQLiteUnitOfWorkFactory
from personlogy.adapters.sqlite_audit import SQLiteRecordStore
from personlogy.application.orchestration import JobService
from personlogy.shared.trace import TraceContext


def test_trace_context_child_preserves_trace_and_restores_parent() -> None:
    root = TraceContext.root(request_id="request-1")
    with root.activate():
        assert TraceContext.current() == root
        child = root.child()
        with child.activate():
            assert TraceContext.current() == child
            assert child.trace_id == root.trace_id
            assert child.parent_span_id == root.span_id
        assert TraceContext.current() == root
    assert TraceContext.current() is None


def test_job_service_persists_trace_and_records_lifecycle(tmp_path: Path) -> None:
    asyncio.run(_test_job_service_persists_trace_and_records_lifecycle(tmp_path))


async def _test_job_service_persists_trace_and_records_lifecycle(tmp_path: Path) -> None:
    database = tmp_path / "personlogy.sqlite3"
    store = SQLiteStore(database)
    audit = SQLiteRecordStore(database)
    service = JobService(
        SQLiteUnitOfWorkFactory(store),
        SQLiteJobQueue(store, poll_interval_seconds=0.01),
        audit_sink=audit,
    )
    request_context = TraceContext.root(request_id="request-2", actor_type="http")

    with request_context.activate():
        submitted = await service.submit(
            kind="conversation.normalize",
            idempotency_key="conversation:trace:1",
            payload={"text": "trace"},
        )

    reloaded = await service.get(submitted.id)
    assert reloaded is not None
    assert reloaded.trace_id == request_context.trace_id
    assert reloaded.request_id == "request-2"
    assert reloaded.parent_span_id == request_context.span_id

    started = await service.start_next(timeout_seconds=0.01)
    assert started is not None
    await service.report_progress(started.id, 50, "normalizing")
    completed = await service.succeed(started.id)

    events = await audit.list(entity_id=str(submitted.id))
    assert [event.event_type for event in events] == [
        "job.submitted",
        "job.started",
        "job.progressed",
        "job.succeeded",
    ]
    assert all(event.trace_id == request_context.trace_id for event in events)
    assert events[0].request_id == "request-2"
    assert events[1].span_id == started.span_id
    assert completed.span_id == started.span_id
