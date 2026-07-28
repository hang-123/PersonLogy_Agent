from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_liveness() -> None:
    response = client.get("/v1/health/live")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["service"] == "person-knowledge-api"


def test_openapi_exposes_versioned_health_route() -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert "/v1/health/live" in response.json()["paths"]
