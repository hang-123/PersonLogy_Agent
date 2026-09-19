from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import create_app


def test_retrieval_search_explicitly_rejects_unsupported_backend() -> None:
    client = TestClient(create_app())
    response = client.get(
        "/v1/retrieval/search",
        params={"project_id": str(uuid4()), "q": "简洁方案"},
    )

    assert response.status_code == 422
    assert "unavailable" in response.text


def test_retrieval_index_rejects_unsupported_backend_before_queueing() -> None:
    client = TestClient(create_app())
    project_id = uuid4()
    response = client.post(
        "/v1/retrieval/index",
        params={"project_id": str(project_id)},
        headers={"X-Idempotency-Key": "retrieval-index-test-1"},
    )

    assert response.status_code == 422
    assert "unavailable" in response.text


def test_retrieval_answer_explicitly_rejects_unsupported_backend() -> None:
    client = TestClient(create_app())
    response = client.post(
        "/v1/retrieval/answer",
        json={"project_id": str(uuid4()), "question": "哪些结论有来源支持?"},
    )

    assert response.status_code == 422
    assert "unavailable" in response.text


def test_source_and_evidence_detail_endpoints_return_not_found_for_unknown_ids() -> None:
    client = TestClient(create_app())
    source_response = client.get(
        f"/v1/source-versions/{uuid4()}", params={"project_id": str(uuid4())}
    )
    evidence_response = client.get(
        f"/v1/evidence/{uuid4()}", params={"project_id": str(uuid4())}
    )

    assert source_response.status_code == 404
    assert evidence_response.status_code == 404
