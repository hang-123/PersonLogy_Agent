from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import create_app


def test_conversation_import_endpoint_returns_job() -> None:
    suffix = str(uuid4())
    response = TestClient(create_app()).post(
        "/v1/conversations/import",
        json={
            "project_name": "API 导入测试",
            "project_slug": f"api-{suffix}",
            "conversation_id": f"conversation-{suffix}",
            "title": "一次对话",
            "messages": [
                {"message_id": "m-1", "role": "user", "content": "保留顺序", "ordinal": 0},
                {
                    "message_id": "m-2",
                    "role": "assistant",
                    "content": "已保留",
                    "ordinal": 1,
                    "parent_message_id": "m-1",
                },
            ],
        },
    )

    assert response.status_code == 202
    body = response.json()
    assert body["imported_message_count"] == 2
    assert body["duplicate_message_count"] == 0
    assert body["job_id"]
