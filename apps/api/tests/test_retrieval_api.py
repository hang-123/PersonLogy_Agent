from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import create_app


def test_retrieval_search_endpoint_returns_project_scoped_shape() -> None:
    client = TestClient(create_app())
    response = client.get(
        "/v1/retrieval/search",
        params={"project_id": str(uuid4()), "q": "简洁方案"},
    )

    assert response.status_code == 200
    assert response.json()["hits"] == []


def test_retrieval_index_endpoint_submits_idempotent_job() -> None:
    client = TestClient(create_app())
    project_id = uuid4()
    response = client.post(
        "/v1/retrieval/index",
        params={"project_id": str(project_id)},
        headers={"X-Idempotency-Key": "retrieval-index-test-1"},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["project_id"] == str(project_id)
    assert body["status"] == "queued"
    assert body["progress"] == 0
