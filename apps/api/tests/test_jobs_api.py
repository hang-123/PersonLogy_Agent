from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import create_app


def test_job_submission_is_idempotent() -> None:
    client = TestClient(create_app())
    headers = {"X-Idempotency-Key": "pdf:abc123"}
    first = client.post("/v1/jobs", json={"kind": "pdf.parse"}, headers=headers)
    second = client.post("/v1/jobs", json={"kind": "pdf.parse"}, headers=headers)

    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["id"] == second.json()["id"]
    assert second.json()["status"] == "queued"


def test_job_list_filters_project_before_limit() -> None:
    client = TestClient(create_app())
    project_id = str(uuid4())
    wanted = client.post(
        "/v1/jobs",
        json={"kind": "test", "payload": {"project_id": project_id}},
        headers={"X-Idempotency-Key": str(uuid4())},
    ).json()
    client.post(
        "/v1/jobs",
        json={"kind": "test", "payload": {"project_id": str(uuid4())}},
        headers={"X-Idempotency-Key": str(uuid4())},
    )
    response = client.get("/v1/jobs", params={"project_id": project_id, "limit": 1})
    assert response.status_code == 200
    assert [job["id"] for job in response.json()] == [wanted["id"]]
