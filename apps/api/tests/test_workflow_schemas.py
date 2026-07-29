import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.modules.ingestion.schemas import EvidenceCreate, SourceCreate

client = TestClient(app)


def test_source_requires_content_or_location() -> None:
    with pytest.raises(ValidationError, match="raw_text, source_url, or storage_path"):
        SourceCreate(
            title="JD",
            source_type="text",
            created_by="tester",
        )


def test_evidence_requires_locator() -> None:
    with pytest.raises(ValidationError, match="locator must identify"):
        EvidenceCreate(
            excerpt="Python is required",
            locator={},
            created_by="tester",
        )


def test_openapi_exposes_ingestion_and_review_commands() -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/v1/sources" in paths
    assert "/v1/sources/{source_id}/evidence" in paths
    assert "/v1/candidates" in paths
    assert "/v1/candidates/{candidate_id}/accept" in paths
    assert "/v1/candidates/{candidate_id}/reject" in paths
    assert "/v1/candidates/{candidate_id}/merge" in paths
    assert "/v1/objects" in paths
