from collections.abc import Awaitable, Callable
from datetime import timedelta
from uuid import UUID

from personlogy.domain.job import Job, JobStatus
from personlogy.ports.queue import JobQueue
from personlogy.ports.unit_of_work import UnitOfWorkFactory

JobHandler = Callable[[Job], Awaitable[None]]


class JobService:
    def __init__(self, uow_factory: UnitOfWorkFactory, queue: JobQueue) -> None:
        self._uow_factory = uow_factory
        self._queue = queue

    async def submit(
        self,
        *,
        kind: str,
        idempotency_key: str,
        payload: dict[str, object],
        max_attempts: int = 3,
        timeout_seconds: int = 900,
    ) -> Job:
        async with self._uow_factory() as uow:
            existing = await uow.jobs.get_by_idempotency_key(idempotency_key)
            if existing is not None:
                return existing
            job = Job(
                kind=kind,
                idempotency_key=idempotency_key,
                payload=payload,
                max_attempts=max_attempts,
                timeout_seconds=timeout_seconds,
            )
            await uow.jobs.add(job)
            await uow.commit()
        await self._queue.enqueue(job.id)
        return job

    async def get(self, job_id: UUID) -> Job | None:
        async with self._uow_factory() as uow:
            return await uow.jobs.get(job_id)

    async def list(self, *, limit: int = 100) -> list[Job]:
        async with self._uow_factory() as uow:
            return await uow.jobs.list(limit=limit)

    async def start_next(self, *, timeout_seconds: float | None = None) -> Job | None:
        job_id = await self._queue.dequeue(timeout_seconds=timeout_seconds)
        if job_id is None:
            return None
        async with self._uow_factory() as uow:
            job = await uow.jobs.get(job_id)
            if job is None or job.status not in {JobStatus.QUEUED, JobStatus.RETRYING}:
                return None
            started = job.start()
            await uow.jobs.save(started)
            await uow.commit()
            return started

    async def report_progress(self, job_id: UUID, progress: int, stage: str) -> Job:
        async with self._uow_factory() as uow:
            job = await self._required_job(uow.jobs.get(job_id))
            updated = job.report_progress(progress, stage)
            await uow.jobs.save(updated)
            await uow.commit()
            return updated

    async def succeed(self, job_id: UUID) -> Job:
        async with self._uow_factory() as uow:
            job = await self._required_job(uow.jobs.get(job_id))
            updated = job.succeed()
            await uow.jobs.save(updated)
            await uow.commit()
            return updated

    async def fail(
        self,
        job_id: UUID,
        reason: str,
        *,
        retryable: bool,
        retry_delay_seconds: int = 30,
    ) -> Job:
        async with self._uow_factory() as uow:
            job = await self._required_job(uow.jobs.get(job_id))
            updated = job.fail(
                reason,
                retryable=retryable,
                retry_delay=timedelta(seconds=retry_delay_seconds),
            )
            await uow.jobs.save(updated)
            await uow.commit()
        if updated.status is JobStatus.RETRYING:
            await self._queue.enqueue(updated.id)
        return updated

    @staticmethod
    async def _required_job(result: Awaitable[Job | None]) -> Job:
        job = await result
        if job is None:
            raise LookupError("job not found")
        return job
