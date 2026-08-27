"""Application service for human review decisions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from uuid import UUID

from personlogy.domain.governance.models import CandidateKind, ReviewTask, ReviewTaskStatus
from personlogy.domain.knowledge.models import VerificationStatus
from personlogy.ports.unit_of_work import UnitOfWork, UnitOfWorkFactory
from personlogy.shared.errors import DomainValidationError


class GovernanceService:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

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
            await _save_candidate_status(uow, task, status)
            updated = task.decide(
                decision,
                reviewer_id=reviewer_id,
                reason=reason,
                after={**(changes or {}), "status": status.value},
            )
            await uow.governance.save_review_task(updated)
            await uow.commit()
            return updated


def _candidate_status(decision: ReviewTaskStatus) -> VerificationStatus:
    return {
        ReviewTaskStatus.APPROVED: VerificationStatus.HUMAN_VERIFIED,
        ReviewTaskStatus.REJECTED: VerificationStatus.REJECTED,
        ReviewTaskStatus.REVISED: VerificationStatus.NEEDS_REVISION,
    }.get(decision, VerificationStatus.MACHINE_CHECKED)


async def _save_candidate_status(
    uow: UnitOfWork, task: ReviewTask, status: VerificationStatus
) -> None:
    if task.candidate_kind is CandidateKind.NODE:
        node = await uow.knowledge.get_node(task.candidate_id)
        if node is None:
            raise DomainValidationError("review task node candidate does not exist")
        await uow.knowledge.save_node(replace(node, status=status))
    elif task.candidate_kind is CandidateKind.CLAIM:
        claim = await uow.knowledge.get_claim(task.candidate_id)
        if claim is None:
            raise DomainValidationError("review task claim candidate does not exist")
        await uow.knowledge.save_claim(replace(claim, status=status))
    else:
        relation = await uow.knowledge.get_relation(task.candidate_id)
        if relation is None:
            raise DomainValidationError("review task relation candidate does not exist")
        await uow.knowledge.save_relation(replace(relation, status=status))
