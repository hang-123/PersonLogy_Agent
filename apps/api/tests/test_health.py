from fastapi.testclient import TestClient

from app.main import create_app


def test_liveness_reports_service() -> None:
    client = TestClient(create_app())
    response = client.get("/v1/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["dependencies"]["gel"] == "not_configured"


def test_readiness_accepts_local_persistence_without_gel() -> None:
    client = TestClient(create_app())
    response = client.get("/v1/health/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
