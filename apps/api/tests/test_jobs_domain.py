from datetime import UTC, datetime, timedelta

import pytest

from personlogy.adapters.memory import InMemoryJobQueue, InMemoryStore, InMemoryUnitOfWorkFactory
from personlogy.application.orchestration import JobService
from personlogy.domain.job import Job, JobStatus
from personlogy.shared.errors import InvalidStateTransitionError


def test_job_retry_preserves_failure_reason_and_attempt() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    job = Job("conversation.normalize", "conversation:1", {}, max_attempts=2)
    running = job.start(now)
    retrying = running.fail(
        "LLM timeout", retryable=True, retry_delay=timedelta(seconds=5), now=now
    )

    assert retrying.status is JobStatus.RETRYING
    assert retrying.attempt == 1
    assert retrying.failure_reason == "LLM timeout"
    assert retrying.next_attempt_at == now + timedelta(seconds=5)
    assert retrying.progress == 0
    assert retrying.stage == "waiting_to_retry"


def test_running_job_reports_timeout_from_started_at() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    job = Job("conversation.normalize", "conversation:timeout", {}, timeout_seconds=10).start(now)

    assert not job.is_timed_out(now + timedelta(seconds=9))
    assert job.is_timed_out(now + timedelta(seconds=10))


def test_terminal_job_cannot_be_started() -> None:
    job = Job("index", "index:1", {}).start().succeed()
    with pytest.raises(InvalidStateTransitionError):
        job.start()


def test_job_service_recovers_stale_running_jobs() -> None:
    import asyncio

    async def run() -> None:
        now = datetime(2026, 1, 1, tzinfo=UTC)
        store = InMemoryStore()
        factory = InMemoryUnitOfWorkFactory(store)
        queue = InMemoryJobQueue()
        service = JobService(factory, queue)
        job = Job("index", "index:stale", {}, timeout_seconds=10).start(now - timedelta(seconds=20))
        async with factory() as uow:
            await uow.jobs.add(job)
            await uow.commit()

        recovered = await service.recover_stale_running(now=now)
        assert len(recovered) == 1
        assert recovered[0].status is JobStatus.RETRYING
        assert recovered[0].progress == 0
        assert await queue.dequeue(timeout_seconds=1) == job.id

    asyncio.run(run())
