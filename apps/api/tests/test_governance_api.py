from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient
from personlogy.domain.governance.models import CandidateKind, ReviewTask, ReviewTaskStatus

from app.main import create_app
from app.modules.governance import router as governance_router


def test_get_review_task_returns_candidate_snapshot(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    task = ReviewTask(
        run_id=uuid4(),
        candidate_id=uuid4(),
        candidate_kind=CandidateKind.CLAIM,
        before={"statement": "需要 Python", "citation_ids": [str(uuid4())]},
        created_at=datetime.now(UTC),
    )

    class FakeGovernanceService:
        async def get_review_task(self, task_id):  # type: ignore[no-untyped-def]
            return task if task_id == task.id else None

    monkeypatch.setattr(governance_router, "governance_service", FakeGovernanceService())
    response = TestClient(create_app()).get(f"/v1/review-tasks/{task.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["candidate_id"] == str(task.candidate_id)
    assert body["candidate_kind"] == "claim"
    assert body["status"] == ReviewTaskStatus.PENDING.value
    assert body["before"]["statement"] == "需要 Python"
    assert body["after"] == {}
