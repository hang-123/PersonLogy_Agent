from collections.abc import Awaitable, Callable
from dataclasses import replace
from datetime import timedelta
from hashlib import sha256
from uuid import UUID

from personlogy.domain.audit import AuditEvent, digest_for
from personlogy.domain.job import Job, JobStatus
from personlogy.ports.audit import AuditSink
from personlogy.ports.queue import JobQueue
from personlogy.ports.unit_of_work import UnitOfWorkFactory
from personlogy.shared.trace import TraceContext

JobHandler = Callable[[Job], Awaitable[None]]


class JobService:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        queue: JobQueue,
        audit_sink: AuditSink | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._queue = queue
        self._audit_sink = audit_sink

    async def submit(
        self,
        *,
        kind: str,
        idempotency_key: str,
        payload: dict[str, object],
        max_attempts: int = 3,
        timeout_seconds: int = 900,
    ) -> Job:
        context = TraceContext.current_or_root()
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
                trace_id=context.trace_id,
                request_id=context.request_id,
                parent_span_id=context.span_id,
            )
            await uow.jobs.add(job)
            await uow.commit()
        await self._queue.enqueue(job.id)
        await self._audit_job(
            "job.submitted",
            job,
            status=job.status.value,
            context=context,
            metadata={
                "kind": job.kind,
                "attempt": job.attempt,
                "idempotency_key_digest": self._digest(job.idempotency_key),
            },
            after=self._state(job),
        )
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
            execution_context = TraceContext.from_job(
                trace_id=started.trace_id,
                span_id=None,
                parent_span_id=started.parent_span_id,
                request_id=started.request_id,
            )
            started = replace(started, span_id=execution_context.span_id)
            await uow.jobs.save(started)
            await uow.commit()
            await self._audit_job(
                "job.started",
                started,
                status=started.status.value,
                context=execution_context,
                metadata={"kind": started.kind, "attempt": started.attempt},
                before=self._state(job),
                after=self._state(started),
            )
            return started

    async def report_progress(self, job_id: UUID, progress: int, stage: str) -> Job:
        async with self._uow_factory() as uow:
            job = await self._required_job(uow.jobs.get(job_id))
            updated = job.report_progress(progress, stage)
            await uow.jobs.save(updated)
            await uow.commit()
            await self._audit_job(
                "job.progressed",
                updated,
                status=updated.status.value,
                metadata={
                    "kind": updated.kind,
                    "attempt": updated.attempt,
                    "progress": updated.progress,
                    "stage": updated.stage,
                },
                before=self._state(job),
                after=self._state(updated),
            )
            return updated

    async def succeed(self, job_id: UUID) -> Job:
        async with self._uow_factory() as uow:
            job = await self._required_job(uow.jobs.get(job_id))
            updated = job.succeed()
            await uow.jobs.save(updated)
            await uow.commit()
            await self._audit_job(
                "job.succeeded",
                updated,
                status=updated.status.value,
                metadata={"kind": updated.kind, "attempt": updated.attempt},
                before=self._state(job),
                after=self._state(updated),
            )
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
        await self._audit_job(
            "job.retrying" if updated.status is JobStatus.RETRYING else "job.failed",
            updated,
            status=updated.status.value,
            reason_code="job_failure",
            metadata={
                "kind": updated.kind,
                "attempt": updated.attempt,
                "retryable": retryable,
                "failure_reason_digest": self._digest(reason),
            },
            before=self._state(job),
            after=self._state(updated),
        )
        return updated

    async def _audit_job(
        self,
        event_type: str,
        job: Job,
        *,
        status: str,
        context: TraceContext | None = None,
        reason_code: str | None = None,
        metadata: dict[str, object] | None = None,
        before: object | None = None,
        after: object | None = None,
    ) -> None:
        if self._audit_sink is None:
            return
        active = context or TraceContext.from_job(
            trace_id=job.trace_id,
            span_id=job.span_id,
            parent_span_id=job.parent_span_id,
            request_id=job.request_id,
        )
        await self._audit_sink.append(
            AuditEvent(
                event_type=event_type,
                status=status,
                trace_id=job.trace_id,
                span_id=active.span_id,
                parent_span_id=active.parent_span_id,
                actor_type=active.actor_type,
                actor_id=active.actor_id,
                entity_type="job",
                entity_id=str(job.id),
                request_id=job.request_id,
                reason_code=reason_code,
                before_digest=self._digest_payload(before),
                after_digest=self._digest_payload(after),
                metadata=self._audit_metadata(job, metadata),
            )
        )

    @staticmethod
    def _digest(value: str) -> str:
        return sha256(value.encode("utf-8")).hexdigest()

    @staticmethod
    def _digest_payload(value: object | None) -> str | None:
        if value is None:
            return None
        return digest_for(value)

    @staticmethod
    def _state(job: Job) -> dict[str, object]:
        return {
            "status": job.status.value,
            "progress": job.progress,
            "stage": job.stage,
            "attempt": job.attempt,
        }

    @staticmethod
    def _audit_metadata(job: Job, metadata: dict[str, object] | None) -> dict[str, object]:
        payload_metadata: dict[str, object] = {}
        for key in ("replay_plan_id", "parent_job_id", "parent_trace_id", "replay_attempt"):
            value = job.payload.get(key)
            if isinstance(value, (str, int)) and not isinstance(value, bool):
                payload_metadata[key] = value
        return {**(metadata or {}), **payload_metadata}

    @staticmethod
    async def _required_job(result: Awaitable[Job | None]) -> Job:
        job = await result
        if job is None:
            raise LookupError("job not found")
        return job
