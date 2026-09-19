"""Transactional application service for the server-side Capture Inbox."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

from personlogy.domain.capture.models import (
    CaptureConflict,
    CapturedEvent,
    CaptureEventResult,
    CaptureReceipt,
    CaptureResultStatus,
    StreamState,
)
from personlogy.domain.job import Job
from personlogy.domain.source.models import Project
from personlogy.ports.unit_of_work import UnitOfWorkFactory
from personlogy.shared.errors import DomainValidationError
from personlogy.shared.trace import TraceContext


class CaptureIngestionService:
    """Accept immutable evidence and schedule exactly one processing job/event.

    The service deliberately writes the inbox row, stream state, and job through
    the same Unit of Work. Queue notification happens after commit in the
    SQLite queue adapter because the committed job row itself is durable queue
    state.
    """

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        *,
        project_slug: str = "personal",
        project_name: str = "个人数字分身",
    ) -> None:
        self._uow_factory = uow_factory
        self._project_slug = project_slug
        self._project_name = project_name

    async def ingest(self, events: tuple[CapturedEvent, ...]) -> CaptureReceipt:
        if not events:
            raise DomainValidationError("capture batch must contain at least one event")
        if len(events) > 100:
            raise DomainValidationError("capture batch cannot contain more than 100 events")
        receipt = CaptureReceipt(results=())
        results: list[CaptureEventResult] = []
        context = TraceContext.current_or_root()

        async with self._uow_factory() as uow:
            for event in events:
                result = await self._ingest_one(uow, event, str(receipt.receipt_id), context)
                results.append(result)
            await uow.commit()

        return replace(receipt, results=tuple(results))

    async def _ingest_one(
        self,
        uow,
        event: CapturedEvent,
        receipt_id: str,
        context: TraceContext,
    ) -> CaptureEventResult:
        by_event_id = await uow.capture.get_by_event_id(event.event_id)
        if by_event_id is not None:
            if by_event_id.payload_hash == event.payload_hash:
                job = await self._job_for_event(uow, event, context)
                return self._already_received(event.event_id, receipt_id, job)
            await uow.capture.add_conflict(
                self._conflict(
                    event,
                    by_event_id,
                    reason="event_id_payload_mismatch",
                )
            )
            return self._conflict_result(event.event_id, receipt_id, "event_id_payload_mismatch")

        by_source = await uow.capture.get_by_source_identity(event.source_identity)
        if by_source is not None:
            if by_source.payload_hash == event.payload_hash:
                job = await self._job_for_event(uow, by_source, context)
                return self._already_received(event.event_id, receipt_id, job)
            await uow.capture.add_conflict(
                self._conflict(
                    event,
                    by_source,
                    reason="source_identity_payload_mismatch",
                )
            )
            return self._conflict_result(
                event.event_id, receipt_id, "source_identity_payload_mismatch"
            )

        by_sequence = await uow.capture.get_by_stream_sequence(
            event.producer_id, event.stream_id, event.sequence
        )
        if by_sequence is not None:
            await uow.capture.add_conflict(
                self._conflict(
                    event,
                    by_sequence,
                    reason="stream_sequence_event_mismatch",
                )
            )
            return self._conflict_result(
                event.event_id, receipt_id, "stream_sequence_event_mismatch"
            )

        project = await uow.sources.get_project_by_slug(self._project_slug)
        if project is None:
            project = Project(name=self._project_name, slug=self._project_slug)
            await uow.sources.add_project(project)

        await uow.capture.add_event(event)
        state = await uow.capture.get_stream_state(event.producer_id, event.stream_id)
        await uow.capture.save_stream_state(_advance_stream_state(state, event))
        job = Job(
            kind="capture.process",
            idempotency_key=f"capture-process:{event.event_id}",
            payload={
                "event_id": str(event.event_id),
                "project_id": str(project.id),
                "project_slug": project.slug,
                "source_kind": event.source_identity.source_kind,
                "source_scope": event.source_identity.source_scope,
                "sequence": event.sequence,
            },
            trace_id=context.trace_id,
            request_id=context.request_id,
            parent_span_id=context.span_id,
        )
        await uow.jobs.add(job)
        return CaptureEventResult(
            event_id=event.event_id,
            status=CaptureResultStatus.ACCEPTED,
            server_receipt_id=receipt_id,
            job_id=job.id,
        )

    async def _job_for_event(self, uow, event: CapturedEvent, context: TraceContext) -> Job:
        key = f"capture-process:{event.event_id}"
        existing = await uow.jobs.get_by_idempotency_key(key)
        if existing is not None:
            return existing
        # This repair path is useful for rows created by an interrupted/older
        # deployment. Normal accepted events create this job in the same tx.
        project = await uow.sources.get_project_by_slug(self._project_slug)
        if project is None:
            project = Project(name=self._project_name, slug=self._project_slug)
            await uow.sources.add_project(project)
        job = Job(
            kind="capture.process",
            idempotency_key=key,
            payload={
                "event_id": str(event.event_id),
                "project_id": str(project.id),
                "project_slug": project.slug,
                "source_kind": event.source_identity.source_kind,
                "source_scope": event.source_identity.source_scope,
                "sequence": event.sequence,
            },
            trace_id=context.trace_id,
            request_id=context.request_id,
            parent_span_id=context.span_id,
        )
        await uow.jobs.add(job)
        return job

    @staticmethod
    def _already_received(event_id: UUID, receipt_id: str, job: Job) -> CaptureEventResult:
        return CaptureEventResult(
            event_id=event_id,
            status=CaptureResultStatus.ALREADY_RECEIVED,
            server_receipt_id=receipt_id,
            job_id=job.id,
        )

    @staticmethod
    def _conflict_result(event_id: UUID, receipt_id: str, reason: str) -> CaptureEventResult:
        return CaptureEventResult(
            event_id=event_id,
            status=CaptureResultStatus.CONFLICT,
            server_receipt_id=receipt_id,
            error_code=reason,
            error_summary="capture identity already contains different raw evidence",
        )

    @staticmethod
    def _conflict(
        incoming: CapturedEvent,
        existing: CapturedEvent,
        *,
        reason: str,
    ) -> CaptureConflict:
        return CaptureConflict(
            source_identity=incoming.source_identity,
            existing_event_id=existing.event_id,
            existing_payload_hash=existing.payload_hash,
            incoming_event_id=incoming.event_id,
            incoming_payload_hash=incoming.payload_hash,
            reason=reason,
        )


def _advance_stream_state(state: StreamState | None, event: CapturedEvent) -> StreamState:
    now = datetime.now(UTC)
    if state is None:
        contiguous = event.sequence if event.sequence == 1 else 0
        return StreamState(
            producer_id=event.producer_id,
            stream_id=event.stream_id,
            next_sequence=event.sequence + 1,
            last_contiguous_received_sequence=contiguous,
            updated_at=now,
        )

    contiguous = state.last_contiguous_received_sequence
    if event.sequence == contiguous + 1:
        contiguous = event.sequence
    return replace(
        state,
        next_sequence=max(state.next_sequence, event.sequence + 1),
        last_contiguous_received_sequence=contiguous,
        updated_at=now,
    )
