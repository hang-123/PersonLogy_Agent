"""Safe replay planning, approval and candidate comparison services."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

from personlogy.application.audit import append_audit_event
from personlogy.application.lineage import add_lineage_link
from personlogy.application.orchestration import JobService
from personlogy.domain.audit import digest_for
from personlogy.domain.job import Job
from personlogy.domain.replay import (
    ReplayComparison,
    ReplayDifferenceDimension,
    ReplayPlan,
    ReplayPlanStatus,
    ReplayVersionSet,
)
from personlogy.ports.audit import AuditSink
from personlogy.ports.lineage import LineageStore
from personlogy.ports.replay import ReplayStore
from personlogy.ports.unit_of_work import UnitOfWorkFactory
from personlogy.shared.errors import DomainValidationError
from personlogy.shared.trace import TraceContext


class ReplayService:
    """Create isolated replay jobs and compare their outputs without publishing."""

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        job_service: JobService,
        replay_store: ReplayStore,
        audit_sink: AuditSink | None = None,
        lineage_store: LineageStore | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._job_service = job_service
        self._replay_store = replay_store
        self._audit_sink = audit_sink
        self._lineage_store = lineage_store

    async def create_plan(
        self,
        *,
        project_id: UUID,
        source_version_id: UUID,
        parent_job_id: UUID | None = None,
        target_schema_version: str | None = None,
        target_compiler_version: str | None = None,
        target_embedding_version: str | None = None,
        target_index_version: int | None = None,
    ) -> ReplayPlan:
        async with self._uow_factory() as uow:
            source_version = await uow.sources.get_version_in_project(
                project_id, source_version_id
            )
            if source_version is None:
                raise DomainValidationError("source version does not belong to project")
            parent_job = await uow.jobs.get(parent_job_id) if parent_job_id else None

        if parent_job_id is not None and parent_job is None:
            raise DomainValidationError("replay parent job was not found")
        if parent_job is not None and not _job_belongs_to_project(parent_job, project_id):
            raise DomainValidationError("replay parent job does not belong to project")

        current = TraceContext.current_or_root()
        parent_trace_id = parent_job.trace_id if parent_job else current.trace_id
        baseline = _baseline_versions(parent_job)
        target = ReplayVersionSet(
            schema_version=target_schema_version or baseline.schema_version,
            compiler_version=target_compiler_version or baseline.compiler_version,
            embedding_version=target_embedding_version or baseline.embedding_version,
            index_version=target_index_version or baseline.index_version,
        )
        plan = ReplayPlan(
            project_id=project_id,
            source_version_id=source_version_id,
            parent_trace_id=parent_trace_id,
            parent_job_id=parent_job_id,
            baseline_input_content_hash=source_version.content_hash,
            baseline_versions=baseline,
            target_input_content_hash=source_version.content_hash,
            target_versions=target,
        )
        await self._replay_store.add_plan(plan)
        await append_audit_event(
            self._audit_sink,
            event_type="replay.plan.created",
            status=plan.status.value,
            entity_type="replay_plan",
            entity_id=str(plan.plan_id),
            context=current,
            metadata=_plan_metadata(plan),
        )
        await add_lineage_link(
            self._lineage_store,
            project_id=project_id,
            from_type="replay_plan",
            from_id=plan.plan_id,
            relation_type="replays",
            to_type="source_version",
            to_id=source_version_id,
        )
        return plan

    async def get_plan(
        self, plan_id: UUID, *, project_id: UUID | None = None
    ) -> ReplayPlan | None:
        plan = await self._replay_store.get_plan(plan_id)
        if plan is not None and project_id is not None and plan.project_id != project_id:
            return None
        return plan

    async def approve(self, plan_id: UUID, *, project_id: UUID | None = None) -> Job:
        plan = await self._require_plan(plan_id)
        if project_id is not None and plan.project_id != project_id:
            raise DomainValidationError("replay plan does not belong to project")
        if plan.status is ReplayPlanStatus.QUEUED and plan.replay_job_id is not None:
            existing = await self._job_service.get(plan.replay_job_id)
            if existing is not None:
                return existing
        if plan.status is not ReplayPlanStatus.PROPOSED:
            raise DomainValidationError("only a proposed replay plan can be approved")

        parent = TraceContext.current_or_root()
        replay_context = TraceContext.root(
            request_id=parent.request_id,
            actor_type=parent.actor_type,
            actor_id=parent.actor_id,
        )
        payload: dict[str, object] = {
            "project_id": str(plan.project_id),
            "source_version_id": str(plan.source_version_id),
            "replay_plan_id": str(plan.plan_id),
            "parent_job_id": str(plan.parent_job_id) if plan.parent_job_id else None,
            "parent_trace_id": plan.parent_trace_id,
            "replay_attempt": 1,
            "schema_version": plan.target_versions.schema_version,
            "compiler_version": plan.target_versions.compiler_version,
            "embedding_version": plan.target_versions.embedding_version,
            "index_version": plan.target_versions.index_version,
            "replay": True,
        }
        with replay_context.activate():
            job = await self._job_service.submit(
                kind="knowledge.compile",
                idempotency_key=f"replay:{plan.plan_id}",
                payload=payload,
            )
        approved = replace(
            plan,
            status=ReplayPlanStatus.QUEUED,
            replay_job_id=job.id,
            approved_at=datetime.now(UTC),
        )
        await self._replay_store.save_plan(approved)
        await append_audit_event(
            self._audit_sink,
            event_type="replay.plan.approved",
            status=approved.status.value,
            entity_type="replay_plan",
            entity_id=str(plan.plan_id),
            context=replay_context,
            metadata={
                **_plan_metadata(approved),
                "replay_job_id": str(job.id),
            },
        )
        await add_lineage_link(
            self._lineage_store,
            project_id=plan.project_id,
            from_type="replay_plan",
            from_id=plan.plan_id,
            relation_type="creates",
            to_type="job",
            to_id=job.id,
        )
        if plan.parent_job_id is not None:
            await add_lineage_link(
                self._lineage_store,
                project_id=plan.project_id,
                from_type="job",
                from_id=plan.parent_job_id,
                relation_type="replay_of",
                to_type="replay_plan",
                to_id=plan.plan_id,
            )
        return job

    async def compare(
        self,
        plan_id: UUID,
        *,
        project_id: UUID | None = None,
        original_output: object | None = None,
        replay_output: object | None = None,
        original_output_digest: str | None = None,
        replay_output_digest: str | None = None,
    ) -> ReplayComparison:
        plan = await self._require_plan(plan_id)
        if project_id is not None and plan.project_id != project_id:
            raise DomainValidationError("replay plan does not belong to project")
        if plan.replay_job_id is None:
            raise DomainValidationError("replay plan has not been approved")
        if original_output is not None and original_output_digest is not None:
            raise DomainValidationError("original output must be object or digest, not both")
        if replay_output is not None and replay_output_digest is not None:
            raise DomainValidationError("replay output must be object or digest, not both")
        original_digest = original_output_digest or (
            digest_for(original_output) if original_output is not None else None
        )
        replay_digest = replay_output_digest or (
            digest_for(replay_output) if replay_output is not None else None
        )
        dimensions = list(_difference_dimensions(plan))
        output_changed: bool | None = None
        if original_digest is not None and replay_digest is not None:
            output_changed = original_digest != replay_digest
            if output_changed:
                dimensions.append(ReplayDifferenceDimension.OUTPUT.value)
        comparison = ReplayComparison(
            project_id=plan.project_id,
            plan_id=plan.plan_id,
            source_version_id=plan.source_version_id,
            replay_job_id=plan.replay_job_id,
            difference_dimensions=tuple(dimensions),
            output_changed=output_changed,
            original_output_digest=original_digest,
            replay_output_digest=replay_digest,
        )
        await self._replay_store.add_comparison(comparison)
        if plan.status is ReplayPlanStatus.QUEUED:
            await self._replay_store.save_plan(
                replace(plan, status=ReplayPlanStatus.COMPLETED)
            )
        await append_audit_event(
            self._audit_sink,
            event_type="replay.comparison.created",
            status="candidate",
            entity_type="replay_comparison",
            entity_id=str(comparison.comparison_id),
            metadata={
                "project_id": str(plan.project_id),
                "replay_plan_id": str(plan.plan_id),
                "replay_job_id": str(plan.replay_job_id),
                "source_version_id": str(plan.source_version_id),
                "difference_dimensions": list(comparison.difference_dimensions),
                "output_changed": output_changed,
                "original_output_digest": original_digest,
                "replay_output_digest": replay_digest,
            },
        )
        await add_lineage_link(
            self._lineage_store,
            project_id=plan.project_id,
            from_type="job",
            from_id=plan.replay_job_id,
            relation_type="produced",
            to_type="replay_comparison",
            to_id=comparison.comparison_id,
        )
        return comparison

    async def list_comparisons(self, plan_id: UUID, *, limit: int = 100) -> list[ReplayComparison]:
        return await self._replay_store.list_comparisons(plan_id, limit=limit)

    async def _require_plan(self, plan_id: UUID) -> ReplayPlan:
        plan = await self._replay_store.get_plan(plan_id)
        if plan is None:
            raise DomainValidationError("replay plan was not found")
        return plan


def _baseline_versions(job: Job | None) -> ReplayVersionSet:
    if job is None:
        return ReplayVersionSet()
    payload = job.payload
    compiler_version = _text(payload, "compiler_version") or _text(payload, "compiler")
    prompt_version = _text(payload, "prompt_version")
    if compiler_version and prompt_version:
        compiler_version = f"{compiler_version}@{prompt_version}"
    return ReplayVersionSet(
        schema_version=_text(payload, "schema_version"),
        compiler_version=compiler_version or "unknown",
        embedding_version=_text(payload, "embedding_version"),
        index_version=_integer(payload.get("index_version")),
    )


def _difference_dimensions(plan: ReplayPlan) -> tuple[str, ...]:
    dimensions: list[str] = []
    if plan.baseline_input_content_hash != plan.target_input_content_hash:
        dimensions.append(ReplayDifferenceDimension.INPUT.value)
    baseline = plan.baseline_versions
    target = plan.target_versions
    if baseline.schema_version != target.schema_version:
        dimensions.append(ReplayDifferenceDimension.SCHEMA.value)
    if baseline.compiler_version != target.compiler_version:
        dimensions.append(ReplayDifferenceDimension.COMPILER.value)
    if baseline.embedding_version != target.embedding_version:
        dimensions.append(ReplayDifferenceDimension.EMBEDDING.value)
    if baseline.index_version != target.index_version:
        dimensions.append(ReplayDifferenceDimension.INDEX.value)
    return tuple(dimensions)


def _plan_metadata(plan: ReplayPlan) -> dict[str, object]:
    return {
        "project_id": str(plan.project_id),
        "source_version_id": str(plan.source_version_id),
        "replay_plan_id": str(plan.plan_id),
        "parent_trace_id": plan.parent_trace_id,
        "parent_job_id": str(plan.parent_job_id) if plan.parent_job_id else None,
        "schema_version": plan.target_versions.schema_version,
        "compiler_version": plan.target_versions.compiler_version,
        "embedding_version": plan.target_versions.embedding_version,
        "index_version": plan.target_versions.index_version,
    }


def _text(payload: Mapping[str, object], key: str) -> str | None:
    value = payload.get(key)
    return value.strip() if isinstance(value, str) and value.strip() else None


def _integer(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _job_belongs_to_project(job: Job, project_id: UUID) -> bool:
    return _text(job.payload, "project_id") == str(project_id)


__all__ = ["ReplayService"]
