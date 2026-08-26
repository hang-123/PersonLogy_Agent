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
