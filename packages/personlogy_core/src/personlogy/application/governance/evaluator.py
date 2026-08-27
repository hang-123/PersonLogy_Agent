"""Conservative, provider-independent governance rules for P5 candidates."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from personlogy.domain.governance.models import (
    CandidateKind,
    ConflictRecord,
    DuplicateGroup,
    GovernanceIssue,
    GovernanceIssueSeverity,
    GovernanceRun,
    GovernanceRunStatus,
    ReviewTask,
)
from personlogy.domain.knowledge.models import Claim
from personlogy.ports.compilation import CompilationBundle


@dataclass(frozen=True, slots=True)
class GovernanceEvaluation:
    run: GovernanceRun
    issues: tuple[GovernanceIssue, ...]
    duplicate_groups: tuple[DuplicateGroup, ...]
    conflicts: tuple[ConflictRecord, ...]
    review_tasks: tuple[ReviewTask, ...]


class GovernanceEvaluator:
    """Evaluate structure/provenance and conservative duplicate/conflict rules.

    Semantic similarity is intentionally not inferred here. A future evaluator
    can implement the same result contract and add an embedding/LLM-backed rule.
    """

    rule_version = "p6-rules-v1"

    def evaluate(
        self, *, project_id: UUID, task_id: UUID, bundle: CompilationBundle
    ) -> GovernanceEvaluation:
        issues: list[GovernanceIssue] = []
        duplicate_groups = _duplicate_groups(project_id, bundle)
        conflicts = _conflict_records(project_id, bundle)
        candidate_ids = tuple(
            [node.id for node in bundle.nodes]
            + [claim.id for claim in bundle.claims]
            + [relation.id for relation in bundle.relations]
        )

        for group in duplicate_groups:
            for candidate_id in group.candidate_ids:
                kind = _candidate_kind(candidate_id, bundle)
                issues.append(
                    GovernanceIssue(
                        run_id=UUID(int=0),
                        candidate_id=candidate_id,
                        candidate_kind=kind,
                        code="duplicate.exact",
                        message=f"candidate duplicates; basis={group.basis}",
                        severity=GovernanceIssueSeverity.WARNING,
                    )
                )
        for conflict in conflicts:
            for candidate_id in conflict.candidate_ids:
                issues.append(
                    GovernanceIssue(
                        run_id=UUID(int=0),
                        candidate_id=candidate_id,
                        candidate_kind=CandidateKind.CLAIM,
                        code="claim.conflict",
                        message=f"claim conflict detected; basis={conflict.basis}",
                        severity=GovernanceIssueSeverity.WARNING,
                    )
                )
        for claim in bundle.claims:
            if not claim.citations:
                issues.append(
                    GovernanceIssue(
                        run_id=UUID(int=0),
                        candidate_id=claim.id,
                        candidate_kind=CandidateKind.CLAIM,
                        code="claim.missing_citation",
                        message="claim has no citation and cannot be written back",
                        severity=GovernanceIssueSeverity.ERROR,
                    )
                )
        for relation in bundle.relations:
            if relation.confidence is not None and relation.confidence < 0.5:
                issues.append(
                    GovernanceIssue(
                        run_id=UUID(int=0),
                        candidate_id=relation.id,
                        candidate_kind=CandidateKind.RELATION,
                        code="relation.low_confidence",
                        message="relation confidence is below 0.5 and needs review",
                        severity=GovernanceIssueSeverity.WARNING,
                    )
                )

        status = (
            GovernanceRunStatus.REJECTED
            if any(issue.severity is GovernanceIssueSeverity.ERROR for issue in issues)
            else GovernanceRunStatus.NEEDS_REVIEW
            if candidate_ids
            else GovernanceRunStatus.PASSED
        )
        run = GovernanceRun(
            project_id=project_id,
            task_id=task_id,
            rule_version=self.rule_version,
            status=status,
            candidate_ids=candidate_ids,
        )
        issues = [
            GovernanceIssue(
                run_id=run.id,
                candidate_id=issue.candidate_id,
                candidate_kind=issue.candidate_kind,
                code=issue.code,
                message=issue.message,
                severity=issue.severity,
            )
            for issue in issues
        ]
        tasks = tuple(
            ReviewTask(
                run_id=run.id,
                candidate_id=candidate_id,
                candidate_kind=_candidate_kind(candidate_id, bundle),
                before=_candidate_snapshot(candidate_id, bundle),
            )
            for candidate_id in candidate_ids
        )
        return GovernanceEvaluation(
            run=run,
            issues=tuple(issues),
            duplicate_groups=tuple(duplicate_groups),
            conflicts=tuple(conflicts),
            review_tasks=tasks,
        )


def _duplicate_groups(project_id: UUID, bundle: CompilationBundle) -> list[DuplicateGroup]:
    groups: list[DuplicateGroup] = []
    for basis, items in (
        ("node.title", _group_by(bundle.nodes, lambda item: _normalize(item.title))),
        ("claim.statement", _group_by(bundle.claims, lambda item: _normalize(item.statement))),
        (
            "relation.endpoints",
            _group_by(
                bundle.relations,
                lambda item: (
                    item.relation_type,
                    str(item.source_id),
                    str(item.target_id),
                ),
            ),
        ),
    ):
        for values in items.values():
            if len(values) > 1:
                groups.append(
                    DuplicateGroup(
                        project_id=project_id,
                        candidate_ids=tuple(item.id for item in values),
                        basis=basis,
                    )
                )
    return groups


def _conflict_records(project_id: UUID, bundle: CompilationBundle) -> list[ConflictRecord]:
    records: list[ConflictRecord] = []
    by_subject: dict[UUID, list[Claim]] = {}
    for claim in bundle.claims:
        by_subject.setdefault(claim.subject_id, []).append(claim)
    for claims in by_subject.values():
        for index, left in enumerate(claims):
            for right in claims[index + 1 :]:
                if _is_negation_pair(left.statement, right.statement):
                    records.append(
                        ConflictRecord(
                            project_id=project_id,
                            candidate_ids=(left.id, right.id),
                            basis=f"same_subject:{left.subject_id}",
                        )
                    )
    return records


def _group_by[ItemT, KeyT: object](
    items: tuple[ItemT, ...], key_factory: Callable[[ItemT], KeyT]
) -> dict[KeyT, list[ItemT]]:
    groups: dict[KeyT, list[ItemT]] = {}
    for item in items:
        key = key_factory(item)
        groups.setdefault(key, []).append(item)
    return groups


def _candidate_kind(candidate_id: UUID, bundle: CompilationBundle) -> CandidateKind:
    if any(item.id == candidate_id for item in bundle.nodes):
        return CandidateKind.NODE
    if any(item.id == candidate_id for item in bundle.claims):
        return CandidateKind.CLAIM
    return CandidateKind.RELATION


def _candidate_snapshot(candidate_id: UUID, bundle: CompilationBundle) -> dict[str, object]:
    for node in bundle.nodes:
        if node.id == candidate_id:
            return {
                "candidate_id": str(node.id),
                "kind": CandidateKind.NODE.value,
                "node_type": node.node_type,
                "title": node.title,
                "properties": node.properties,
                "status": "machine_checked",
            }
    for claim in bundle.claims:
        if claim.id == candidate_id:
            return {
                "candidate_id": str(claim.id),
                "kind": CandidateKind.CLAIM.value,
                "subject_id": str(claim.subject_id),
                "statement": claim.statement,
                "confidence": claim.confidence,
                "citation_ids": [str(item.id) for item in claim.citations],
                "status": "machine_checked",
            }
    for relation in bundle.relations:
        if relation.id == candidate_id:
            return {
                "candidate_id": str(relation.id),
                "kind": CandidateKind.RELATION.value,
                "relation_type": relation.relation_type,
                "source_id": str(relation.source_id),
                "target_id": str(relation.target_id),
                "confidence": relation.confidence,
                "citation_ids": [str(item) for item in relation.citation_ids],
                "properties": relation.properties,
                "status": "machine_checked",
            }
    raise ValueError(f"candidate not found in compilation bundle: {candidate_id}")


def _normalize(value: str) -> str:
    return " ".join(value.lower().split())


def _is_negation_pair(left: str, right: str) -> bool:
    left_base, left_negated = _negation_signature(left)
    right_base, right_negated = _negation_signature(right)
    return left_base == right_base and left_negated != right_negated


def _negation_signature(value: str) -> tuple[str, bool]:
    normalized = _normalize(value)
    tokens = ("not ", "never ", "without ", "不", "无", "没有", "不是", "否")
    for token in tokens:
        if token in normalized:
            return normalized.replace(token, "", 1), True
    return normalized, False
