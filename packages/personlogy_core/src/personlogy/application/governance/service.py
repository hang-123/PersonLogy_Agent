"""Application service for human review decisions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from uuid import UUID

from personlogy.application.audit import append_audit_event
from personlogy.application.lineage import add_lineage_link
from personlogy.domain.audit import digest_for
from personlogy.domain.governance.models import CandidateKind, ReviewTask, ReviewTaskStatus
from personlogy.domain.knowledge.models import VerificationStatus
from personlogy.ports.audit import AuditSink
from personlogy.ports.lineage import LineageStore
from personlogy.ports.unit_of_work import UnitOfWork, UnitOfWorkFactory
from personlogy.shared.errors import DomainValidationError


class GovernanceService:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        audit_sink: AuditSink | None = None,
        lineage_store: LineageStore | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._audit_sink = audit_sink
        self._lineage_store = lineage_store

    async def list_review_tasks(self, *, limit: int = 100) -> list[ReviewTask]:
        async with self._uow_factory() as uow:
            return await uow.governance.list_review_tasks(limit=limit)

    async def decide_review_task(
        self,
        task_id: UUID,
        *,
        decision: ReviewTaskStatus,
        reviewer_id: str,
        reason: str,
        expected_version: int | None = None,
        changes: Mapping[str, object] | None = None,
    ) -> ReviewTask:
        async with self._uow_factory() as uow:
            task = await uow.governance.get_review_task(task_id)
            if task is None:
                raise DomainValidationError("review task does not exist")
            if expected_version is not None and expected_version != task.version:
                raise DomainValidationError("review task version is stale")

            status = _candidate_status(decision)
            project_id = await _save_candidate_status(uow, task, status)
            updated = task.decide(
                decision,
                reviewer_id=reviewer_id,
                reason=reason,
                after={**(changes or {}), "status": status.value},
            )
            await uow.governance.save_review_task(updated)
            await uow.commit()
            audit_event = await append_audit_event(
                self._audit_sink,
                event_type="review_task.decided",
                status=updated.status.value,
                entity_type="review_task",
                entity_id=str(updated.id),
                before={
                    "status": task.status.value,
                    "version": task.version,
                    "candidate_id": str(task.candidate_id),
                },
                after={
                    "status": updated.status.value,
                    "version": updated.version,
                    "candidate_id": str(updated.candidate_id),
                },
                metadata={
                    "candidate_kind": updated.candidate_kind.value,
                    "decision": decision.value,
                    "reason_digest": digest_for(reason),
                    "version": updated.version,
                },
            )
            await add_lineage_link(
                self._lineage_store,
                project_id=project_id,
                from_type="review_task",
                from_id=updated.id,
                relation_type="reviews",
                to_type=updated.candidate_kind.value,
                to_id=updated.candidate_id,
            )
            if audit_event is not None:
                await add_lineage_link(
                    self._lineage_store,
                    project_id=project_id,
                    from_type="review_task",
                    from_id=updated.id,
                    relation_type="recorded_by",
                    to_type="audit_event",
                    to_id=audit_event.event_id,
                )
            return updated


def _candidate_status(decision: ReviewTaskStatus) -> VerificationStatus:
    return {
        ReviewTaskStatus.APPROVED: VerificationStatus.HUMAN_VERIFIED,
        ReviewTaskStatus.REJECTED: VerificationStatus.REJECTED,
        ReviewTaskStatus.REVISED: VerificationStatus.NEEDS_REVISION,
    }.get(decision, VerificationStatus.MACHINE_CHECKED)


async def _save_candidate_status(
    uow: UnitOfWork, task: ReviewTask, status: VerificationStatus
) -> UUID:
    if task.candidate_kind is CandidateKind.NODE:
        node = await uow.knowledge.get_node(task.candidate_id)
        if node is None:
            raise DomainValidationError("review task node candidate does not exist")
        await uow.knowledge.save_node(replace(node, status=status))
        return node.project_id
    elif task.candidate_kind is CandidateKind.CLAIM:
        claim = await uow.knowledge.get_claim(task.candidate_id)
        if claim is None:
            raise DomainValidationError("review task claim candidate does not exist")
        await uow.knowledge.save_claim(replace(claim, status=status))
        return claim.project_id
    else:
        relation = await uow.knowledge.get_relation(task.candidate_id)
        if relation is None:
            raise DomainValidationError("review task relation candidate does not exist")
        await uow.knowledge.save_relation(replace(relation, status=status))
        return relation.project_id
