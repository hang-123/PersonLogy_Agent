"""Application service for controlled publication of governed knowledge."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

from personlogy.application.audit import append_audit_event
from personlogy.application.lineage import add_lineage_link
from personlogy.domain.audit import digest_for
from personlogy.domain.governance.models import CandidateKind, ReviewTaskStatus
from personlogy.domain.job import Job
from personlogy.domain.knowledge.models import Claim, KnowledgeNode, VerificationStatus
from personlogy.domain.relation.models import Relation
from personlogy.domain.writeback.models import (
    CandidateRef,
    WritebackItem,
    WritebackRecord,
    WritebackStatus,
)
from personlogy.ports.audit import AuditSink
from personlogy.ports.ingestion import ObjectStorage
from personlogy.ports.lineage import LineageStore
from personlogy.ports.schema_management import SchemaRegistry
from personlogy.ports.unit_of_work import UnitOfWork, UnitOfWorkFactory
from personlogy.ports.writeback import (
    SchemaWritebackValidator,
    WritebackAuthorizer,
)
from personlogy.shared.errors import DomainValidationError
from personlogy.shared.trace import TraceContext

_PUBLISHABLE = frozenset(
    {VerificationStatus.HUMAN_VERIFIED, VerificationStatus.READY_FOR_WRITEBACK}
)
CandidateObject = KnowledgeNode | Claim | Relation


class LocalWritebackAuthorizer:
    """Development-only authorizer; production must inject a project policy."""

    def __init__(self, *, environment: str) -> None:
        self._allowed = environment in {"local", "test"}

    async def authorize(
        self, *, project_id: UUID, actor_type: str, actor_id: str | None
    ) -> bool:
        del project_id
        return self._allowed and bool(actor_type.strip())


class NoopSchemaWritebackValidator:
    """Structural fallback until SchemaRegistry exposes a writeback validator."""

    async def validate(
        self, *, namespace: str, version: int, project_id: UUID, candidate_ids: tuple[UUID, ...]
    ) -> None:
        del project_id, candidate_ids
        if not namespace.strip() or version < 1:
            raise DomainValidationError("writeback schema namespace and version are required")


class RegistrySchemaWritebackValidator:
    """Validate that the requested schema snapshot is registered and immutable."""

    def __init__(self, registry: SchemaRegistry) -> None:
        self._registry = registry

    async def validate(
        self, *, namespace: str, version: int, project_id: UUID, candidate_ids: tuple[UUID, ...]
    ) -> None:
        del project_id, candidate_ids
        if not namespace.strip() or version < 1:
            raise DomainValidationError("writeback schema namespace and version are required")
        snapshot = await self._registry.get_snapshot(namespace, version)
        if snapshot is None:
            raise DomainValidationError("writeback schema snapshot does not exist")


class WritebackService:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        okf_storage: ObjectStorage,
        *,
        authorizer: WritebackAuthorizer,
        schema_validator: SchemaWritebackValidator | None = None,
        audit_sink: AuditSink | None = None,
        lineage_store: LineageStore | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._okf_storage = okf_storage
        self._authorizer = authorizer
        self._schema_validator = schema_validator or NoopSchemaWritebackValidator()
        self._audit_sink = audit_sink
        self._lineage_store = lineage_store

    async def get(self, record_id: UUID) -> WritebackRecord | None:
        async with self._uow_factory() as uow:
            return await uow.writebacks.get(record_id)

    async def list_items(self, record_id: UUID) -> list[WritebackItem]:
        async with self._uow_factory() as uow:
            return await uow.writebacks.list_items(record_id)

    async def submit(
        self,
        *,
        project_id: UUID,
        governance_run_id: UUID,
        candidates: tuple[CandidateRef, ...],
        idempotency_key: str,
        schema_namespace: str = "personlogy",
        schema_version: int = 1,
    ) -> tuple[WritebackRecord, Job]:
        context = TraceContext.current_or_root()
        if not await self._authorizer.authorize(
            project_id=project_id,
            actor_type=context.actor_type,
            actor_id=context.actor_id,
        ):
            await append_audit_event(
                self._audit_sink,
                event_type="writeback.preflight_failed",
                status="denied",
                entity_type="writeback",
                entity_id=idempotency_key,
                context=context,
                reason_code="writeback_permission_denied",
                metadata={"project_id": str(project_id)},
            )
            raise DomainValidationError("writeback permission denied")

        normalized = _normalize_candidates(candidates)
        request_digest = digest_for(
            {
                "project_id": str(project_id),
                "governance_run_id": str(governance_run_id),
                "schema_namespace": schema_namespace,
                "schema_version": schema_version,
                "candidates": [
                    {
                        "candidate_id": str(item.candidate_id),
                        "candidate_kind": item.candidate_kind.value,
                        "expected_review_version": item.expected_review_version,
                    }
                    for item in normalized
                ],
            }
        )
        async with self._uow_factory() as uow:
            existing = await uow.writebacks.get_by_idempotency_key(idempotency_key)
            if existing is not None:
                if existing.request_digest != request_digest:
                    raise DomainValidationError("writeback idempotency key has different content")
                job = await self._required_job(uow, existing.effects_job_id)
                return existing, job

            objects = await self._load_and_validate(
                uow,
                project_id=project_id,
                governance_run_id=governance_run_id,
                candidates=normalized,
            )
            await self._schema_validator.validate(
                namespace=schema_namespace,
                version=schema_version,
                project_id=project_id,
                candidate_ids=tuple(item.candidate_id for item in normalized),
            )
            candidate_digest = digest_for(
                [_candidate_payload(item, objects[item.candidate_id]) for item in normalized]
            )
            record = WritebackRecord(
                project_id=project_id,
                governance_run_id=governance_run_id,
                schema_namespace=schema_namespace,
                schema_version=schema_version,
                idempotency_key=idempotency_key,
                request_digest=request_digest,
                candidate_digest=candidate_digest,
                candidates=normalized,
                committed_at=datetime.now(UTC),
            )
            await uow.writebacks.add(record)
            for item in normalized:
                candidate = objects[item.candidate_id]
                before = _candidate_status(candidate)
                after_candidate = _publish(candidate)
                await _save_candidate(uow, after_candidate)
                await uow.writebacks.add_item(
                    WritebackItem(
                        record_id=record.id,
                        candidate_id=item.candidate_id,
                        candidate_kind=item.candidate_kind,
                        before_status=before,
                        after_status=_candidate_status(after_candidate),
                        before_digest=digest_for(_candidate_payload(item, candidate)),
                        after_digest=digest_for(_candidate_payload(item, after_candidate)),
                    )
                )

            job = Job(
                kind="knowledge.writeback.effects",
                idempotency_key=f"knowledge-writeback-effects:{record.id}",
                payload={"writeback_id": str(record.id), "project_id": str(project_id)},
                trace_id=context.trace_id,
                request_id=context.request_id,
                parent_span_id=context.span_id,
            )
            await uow.jobs.add(job)
            record = replace(record, effects_job_id=job.id)
            await uow.writebacks.save(record)
            await uow.commit()

        audit_event = await append_audit_event(
            self._audit_sink,
            event_type="writeback.committed",
            status=record.status.value,
            entity_type="writeback_record",
            entity_id=str(record.id),
            context=context,
            after={"status": record.status.value, "candidate_count": len(record.candidates)},
            metadata={
                "project_id": str(project_id),
                "governance_run_id": str(governance_run_id),
                "schema_namespace": schema_namespace,
                "schema_version": schema_version,
                "entity_count": len(record.candidates),
            },
        )
        await add_lineage_link(
            self._lineage_store,
            project_id=record.project_id,
            from_type="writeback_record",
            from_id=record.id,
            relation_type="derived_from",
            to_type="governance_run",
            to_id=record.governance_run_id,
        )
        await add_lineage_link(
            self._lineage_store,
            project_id=record.project_id,
            from_type="writeback_record",
            from_id=record.id,
            relation_type="scheduled_as",
            to_type="job",
            to_id=job.id,
        )
        for item in record.candidates:
            await add_lineage_link(
                self._lineage_store,
                project_id=record.project_id,
                from_type="writeback_record",
                from_id=record.id,
                relation_type="publishes",
                to_type=item.candidate_kind.value,
                to_id=item.candidate_id,
            )
        if audit_event is not None:
            await add_lineage_link(
                self._lineage_store,
                project_id=record.project_id,
                from_type="writeback_record",
                from_id=record.id,
                relation_type="recorded_by",
                to_type="audit_event",
                to_id=audit_event.event_id,
            )
        return record, job

    async def process_effects_job(self, job: Job) -> WritebackRecord:
        if job.kind != "knowledge.writeback.effects":
            raise DomainValidationError(f"unsupported writeback job kind: {job.kind}")
        record_id = _payload_uuid(job, "writeback_id")
        try:
            return await self._process_effects_job(job, record_id)
        except Exception as error:
            await self._mark_effects_failed(record_id, error)
            raise

    async def _process_effects_job(self, job: Job, record_id: UUID) -> WritebackRecord:
        async with self._uow_factory() as uow:
            record = await uow.writebacks.get(record_id)
            if record is None:
                raise DomainValidationError("writeback record does not exist")
            if record.status is WritebackStatus.COMPLETED:
                return record
            if record.status is WritebackStatus.REVERTED:
                raise DomainValidationError("reverted writeback cannot run effects")
            objects = await self._load_objects(uow, record.candidates)
            items = await uow.writebacks.list_items(record.id)
            okf = _build_okf(record, objects, items)
            okf_key = (
                f"projects/{record.project_id}/writebacks/{record.id}/"
                f"okf-v{record.schema_version}.json"
            )
            await self._okf_storage.put(
                okf_key,
                json.dumps(okf, ensure_ascii=False, indent=2).encode("utf-8"),
            )
            index_key = f"retrieval-index:{record.project_id}:writeback:{record.id}"
            index_job = await uow.jobs.get_by_idempotency_key(index_key)
            if index_job is None:
                index_job = Job(
                    kind="retrieval.index",
                    idempotency_key=index_key,
                    payload={
                        "project_id": str(record.project_id),
                        "writeback_id": str(record.id),
                    },
                    trace_id=job.trace_id,
                    request_id=job.request_id,
                    parent_span_id=job.span_id,
                )
                await uow.jobs.add(index_job)
            completed = record.complete(okf_object_key=okf_key, index_job_id=index_job.id)
            await uow.writebacks.save(completed)
            await uow.commit()

        audit_event = await append_audit_event(
            self._audit_sink,
            event_type="writeback.effects_succeeded",
            status=completed.status.value,
            entity_type="writeback_record",
            entity_id=str(completed.id),
            after={"status": completed.status.value, "okf_object_key": completed.okf_object_key},
            metadata={
                "project_id": str(completed.project_id),
                "index_job_id": str(completed.index_job_id) if completed.index_job_id else None,
            },
        )
        if completed.okf_object_key is not None:
            await add_lineage_link(
                self._lineage_store,
                project_id=completed.project_id,
                from_type="writeback_record",
                from_id=completed.id,
                relation_type="materialized_as",
                to_type="okf_object",
                to_id=completed.okf_object_key,
            )
        if completed.index_job_id is not None:
            await add_lineage_link(
                self._lineage_store,
                project_id=completed.project_id,
                from_type="writeback_record",
                from_id=completed.id,
                relation_type="scheduled_as",
                to_type="job",
                to_id=completed.index_job_id,
            )
        if audit_event is not None:
            await add_lineage_link(
                self._lineage_store,
                project_id=completed.project_id,
                from_type="writeback_record",
                from_id=completed.id,
                relation_type="recorded_by",
                to_type="audit_event",
                to_id=audit_event.event_id,
            )
        return completed

    async def _mark_effects_failed(self, record_id: UUID, error: Exception) -> None:
        error_digest = digest_for(
            {"error_type": type(error).__name__, "message": str(error)}
        )
        async with self._uow_factory() as uow:
            record = await uow.writebacks.get(record_id)
            if record is None or record.status in {
                WritebackStatus.COMPLETED,
                WritebackStatus.REVERTED,
            }:
                return
            failed = record.fail_retryably(
                error_code="writeback_effects_failed",
                error_digest=error_digest,
            )
            await uow.writebacks.save(failed)
            await uow.commit()
        audit_event = await append_audit_event(
            self._audit_sink,
            event_type="writeback.effects_failed",
            status=failed.status.value,
            entity_type="writeback_record",
            entity_id=str(failed.id),
            after={"status": failed.status.value, "error_code": failed.error_code},
            reason_code=failed.error_code,
            metadata={"error_digest": error_digest},
        )
        if audit_event is not None:
            await add_lineage_link(
                self._lineage_store,
                project_id=failed.project_id,
                from_type="writeback_record",
                from_id=failed.id,
                relation_type="recorded_by",
                to_type="audit_event",
                to_id=audit_event.event_id,
            )

    async def _load_and_validate(
        self,
        uow: UnitOfWork,
        *,
        project_id: UUID,
        governance_run_id: UUID,
        candidates: tuple[CandidateRef, ...],
    ) -> dict[UUID, CandidateObject]:
        tasks = await uow.governance.list_review_tasks(limit=10000)
        objects = await self._load_objects(uow, candidates)
        for item in candidates:
            candidate = objects[item.candidate_id]
            if _candidate_project(candidate) != project_id:
                raise DomainValidationError("writeback candidate is outside the project")
            status = _candidate_status(candidate)
            if status not in _PUBLISHABLE:
                raise DomainValidationError("candidate is not approved for writeback")
            task = next(
                (
                    task
                    for task in tasks
                    if task.run_id == governance_run_id
                    and task.candidate_id == item.candidate_id
                    and task.candidate_kind is item.candidate_kind
                ),
                None,
            )
            if task is None or task.status is not ReviewTaskStatus.APPROVED:
                raise DomainValidationError("candidate has no approved review task")
            if (
                item.expected_review_version is not None
                and task.version != item.expected_review_version
            ):
                raise DomainValidationError("review task version is stale")
            await _validate_dependencies(uow, project_id, candidate, candidates)
        return objects

    async def _load_objects(
        self, uow: UnitOfWork, candidates: tuple[CandidateRef, ...]
    ) -> dict[UUID, CandidateObject]:
        objects: dict[UUID, CandidateObject] = {}
        candidate: CandidateObject | None
        for item in candidates:
            if item.candidate_kind is CandidateKind.NODE:
                candidate = await uow.knowledge.get_node(item.candidate_id)
            elif item.candidate_kind is CandidateKind.CLAIM:
                candidate = await uow.knowledge.get_claim(item.candidate_id)
            else:
                candidate = await uow.knowledge.get_relation(item.candidate_id)
            if candidate is None:
                raise DomainValidationError("writeback candidate does not exist")
            objects[item.candidate_id] = candidate
        return objects

    @staticmethod
    async def _required_job(uow: UnitOfWork, job_id: UUID | None) -> Job:
        if job_id is None:
            raise DomainValidationError("writeback effects job is missing")
        job = await uow.jobs.get(job_id)
        if job is None:
            raise DomainValidationError("writeback effects job does not exist")
        return job


def _normalize_candidates(candidates: tuple[CandidateRef, ...]) -> tuple[CandidateRef, ...]:
    if not candidates:
        raise DomainValidationError("at least one writeback candidate is required")
    normalized = tuple(
        sorted(candidates, key=lambda item: (item.candidate_kind.value, str(item.candidate_id)))
    )
    if len({(item.candidate_kind, item.candidate_id) for item in normalized}) != len(normalized):
        raise DomainValidationError("writeback candidates must be unique")
    return normalized


def _candidate_status(candidate: CandidateObject) -> VerificationStatus:
    status = getattr(candidate, "status", None)
    if not isinstance(status, VerificationStatus):
        raise DomainValidationError("candidate status is invalid")
    return status


def _candidate_project(candidate: CandidateObject) -> UUID:
    project_id = getattr(candidate, "project_id", None)
    if not isinstance(project_id, UUID):
        raise DomainValidationError("candidate project is invalid")
    return project_id


def _publish(candidate: CandidateObject) -> CandidateObject:
    if _candidate_status(candidate) is VerificationStatus.READY_FOR_WRITEBACK:
        return candidate
    return replace(candidate, status=VerificationStatus.READY_FOR_WRITEBACK)


async def _save_candidate(uow: UnitOfWork, candidate: CandidateObject) -> None:
    if isinstance(candidate, KnowledgeNode):
        await uow.knowledge.save_node(candidate)
    elif isinstance(candidate, Claim):
        await uow.knowledge.save_claim(candidate)
    elif isinstance(candidate, Relation):
        await uow.knowledge.save_relation(candidate)
    else:  # pragma: no cover - guarded by candidate loading
        raise DomainValidationError("unsupported writeback candidate")


async def _validate_dependencies(
    uow: UnitOfWork,
    project_id: UUID,
    candidate: CandidateObject,
    submitted: tuple[CandidateRef, ...],
) -> None:
    submitted_ids = {item.candidate_id for item in submitted}
    if isinstance(candidate, Claim):
        if not candidate.citations:
            raise DomainValidationError("claim must have a citation")
        node = await uow.knowledge.get_node(candidate.subject_id)
        if node is None or node.project_id != project_id:
            raise DomainValidationError("claim subject is outside the project")
        if node.status not in _PUBLISHABLE and node.id not in submitted_ids:
            raise DomainValidationError("claim subject is not approved for writeback")
    elif isinstance(candidate, Relation):
        if not candidate.citation_ids:
            raise DomainValidationError("relation must have a citation")
        relation_type = await uow.knowledge.get_relation_type(candidate.relation_type)
        source = await uow.knowledge.get_node(candidate.source_id)
        target = await uow.knowledge.get_node(candidate.target_id)
        if relation_type is None or source is None or target is None:
            raise DomainValidationError("relation dependencies do not exist")
        if (
            source.project_id != project_id
            or target.project_id != project_id
            or (source.status not in _PUBLISHABLE and source.id not in submitted_ids)
            or (target.status not in _PUBLISHABLE and target.id not in submitted_ids)
        ):
            raise DomainValidationError("relation dependency is not approved for writeback")


def _candidate_payload(ref: CandidateRef, candidate: CandidateObject) -> dict[str, object]:
    payload: dict[str, object] = {
        "candidate_id": str(ref.candidate_id),
        "candidate_kind": ref.candidate_kind.value,
        "status": _candidate_status(candidate).value,
    }
    for name in (
        "node_type",
        "title",
        "statement",
        "properties",
        "confidence",
        "relation_type",
        "source_id",
        "target_id",
        "citation_ids",
    ):
        value = getattr(candidate, name, None)
        if isinstance(value, tuple):
            payload[name] = [str(item) for item in value]
        elif isinstance(value, UUID):
            payload[name] = str(value)
        elif value is not None:
            payload[name] = value
    return payload


def _build_okf(
    record: WritebackRecord,
    objects: Mapping[UUID, CandidateObject],
    items: list[WritebackItem],
) -> dict[str, object]:
    return {
        "okf_version": "0.2",
        "provenance": {
            "writeback_id": str(record.id),
            "governance_run_id": str(record.governance_run_id),
            "project_id": str(record.project_id),
            "schema_namespace": record.schema_namespace,
            "schema_version": record.schema_version,
            "candidate_digest": record.candidate_digest,
            "generated_at": datetime.now(UTC).isoformat(),
        },
        "candidates": [
            {
                **_candidate_payload(ref, objects[ref.candidate_id]),
                "before_digest": next(
                    item.before_digest for item in items if item.candidate_id == ref.candidate_id
                ),
                "after_digest": next(
                    item.after_digest for item in items if item.candidate_id == ref.candidate_id
                ),
            }
            for ref in record.candidates
        ],
    }


def _payload_uuid(job: Job, key: str) -> UUID:
    value = job.payload.get(key)
    if not isinstance(value, str):
        raise DomainValidationError(f"writeback job payload field is missing: {key}")
    try:
        return UUID(value)
    except ValueError as error:
        raise DomainValidationError(f"writeback job payload field is invalid: {key}") from error


__all__ = [
    "LocalWritebackAuthorizer",
    "NoopSchemaWritebackValidator",
    "RegistrySchemaWritebackValidator",
    "WritebackService",
]
