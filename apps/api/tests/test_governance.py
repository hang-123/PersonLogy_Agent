from dataclasses import replace
from uuid import uuid4

from personlogy.application.compilation import DocumentHeuristicCompiler
from personlogy.application.governance import GovernanceEvaluator
from personlogy.domain.source.models import ContentBlock, Project


def test_governance_marks_exact_duplicates_for_review() -> None:
    project = Project("治理测试", "governance-duplicate")
    blocks = (
        ContentBlock(uuid4(), 0, "重复概念", "hash-1", {"page": 1}),
        ContentBlock(uuid4(), 1, "重复概念", "hash-2", {"page": 2}),
    )
    bundle = DocumentHeuristicCompiler().compile(project_id=project.id, blocks=blocks)

    evaluation = GovernanceEvaluator().evaluate(
        project_id=project.id,
        task_id=uuid4(),
        bundle=bundle,
    )

    assert evaluation.run.status.value == "needs_review"
    assert evaluation.duplicate_groups
    assert any(issue.code == "duplicate.exact" for issue in evaluation.issues)
    assert len(evaluation.review_tasks) == 5


def test_governance_keeps_conflicting_claims_and_creates_conflict_record() -> None:
    project = Project("治理测试", "governance-conflict")
    blocks = (
        ContentBlock(uuid4(), 0, "用户喜欢 Python。", "hash-1", {"page": 1}),
        ContentBlock(uuid4(), 1, "用户不喜欢 Python。", "hash-2", {"page": 2}),
    )
    initial = DocumentHeuristicCompiler().compile(project_id=project.id, blocks=blocks)
    claims = (
        replace(initial.claims[0], statement="用户喜欢 Python"),
        replace(
            initial.claims[1],
            subject_id=initial.claims[0].subject_id,
            statement="用户不喜欢 Python",
        ),
    )
    bundle = replace(initial, claims=claims)

    evaluation = GovernanceEvaluator().evaluate(
        project_id=project.id,
        task_id=uuid4(),
        bundle=bundle,
    )

    assert len(evaluation.conflicts) == 1
    assert len(evaluation.conflicts[0].candidate_ids) == 2
    assert evaluation.run.status.value == "needs_review"
