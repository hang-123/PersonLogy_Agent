import asyncio
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.main import create_app
from personlogy.adapters.sqlite import SQLiteStore, SQLiteUnitOfWorkFactory
from personlogy.application.capture import CaptureIngestionService
from personlogy.domain.capture.models import (
    CapturedEvent,
    CaptureResultStatus,
    CaptureSourceIdentity,
)


def _event(*, number: int = 1, payload: dict[str, object] | None = None) -> CapturedEvent:
    value = payload or {"message": {"role": "user", "text": f"event-{number}"}}
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return CapturedEvent(
        schema_version=1,
        event_id=UUID(int=number),
        producer_id="test-producer",
        stream_id="test-stream",
        sequence=number,
        source_identity=CaptureSourceIdentity(
            source_kind="codex",
            source_scope="project-a",
            session_key="session-a",
            source_item_key=f"item-{number}",
            source_revision=0,
        ),
        captured_at=datetime(2026, 9, 19, tzinfo=UTC),
        rule_version="test-rules-v1",
        payload_hash=hashlib.sha256(encoded.encode()).hexdigest(),
        payload=value,
    )


def test_capture_is_idempotent_and_creates_one_job(tmp_path: Path) -> None:
    async def run() -> None:
        store = SQLiteStore(tmp_path / "capture.sqlite3")
        service = CaptureIngestionService(SQLiteUnitOfWorkFactory(store))
        event = _event()

        first = await service.ingest((event,))
        repeated = [await service.ingest((event,)) for _ in range(10)]

        assert first.results[0].status is CaptureResultStatus.ACCEPTED
        assert all(
            item.results[0].status is CaptureResultStatus.ALREADY_RECEIVED
            for item in repeated
        )
        connection = store.connect()
        try:
            assert connection.execute("SELECT COUNT(*) FROM capture_inbox_event").fetchone()[0] == 1
            assert connection.execute("SELECT COUNT(*) FROM job").fetchone()[0] == 1
            assert (
                connection.execute("SELECT COUNT(*) FROM capture_stream_state").fetchone()[0]
                == 1
            )
        finally:
            connection.close()

    asyncio.run(run())


def test_capture_conflicts_and_batch_partial_success(tmp_path: Path) -> None:
    async def run() -> None:
        store = SQLiteStore(tmp_path / "capture.sqlite3")
        service = CaptureIngestionService(SQLiteUnitOfWorkFactory(store))
        accepted = _event()
        # Reuse the first source identity but change the immutable payload.
        source_conflict = CapturedEvent(
            schema_version=accepted.schema_version,
            event_id=uuid4(),
            producer_id=accepted.producer_id,
            stream_id=accepted.stream_id,
            sequence=2,
            source_identity=accepted.source_identity,
            captured_at=accepted.captured_at,
            rule_version=accepted.rule_version,
            payload_hash="b" * 64,
            payload={"different": True},
        )
        sequence_conflict = CapturedEvent(
            schema_version=accepted.schema_version,
            event_id=uuid4(),
            producer_id=accepted.producer_id,
            stream_id=accepted.stream_id,
            sequence=1,
            source_identity=CaptureSourceIdentity("codex", "project-a", "session-a", "item-3"),
            captured_at=accepted.captured_at,
            rule_version=accepted.rule_version,
            payload_hash="c" * 64,
            payload={"different": "sequence"},
        )
        new_event = _event(number=4)

        receipt = await service.ingest((accepted, source_conflict, sequence_conflict, new_event))
        assert [item.status for item in receipt.results] == [
            CaptureResultStatus.ACCEPTED,
            CaptureResultStatus.CONFLICT,
            CaptureResultStatus.CONFLICT,
            CaptureResultStatus.ACCEPTED,
        ]
        connection = store.connect()
        try:
            assert connection.execute("SELECT COUNT(*) FROM capture_inbox_event").fetchone()[0] == 2
            assert connection.execute("SELECT COUNT(*) FROM job").fetchone()[0] == 2
            assert (
                connection.execute("SELECT COUNT(*) FROM capture_inbox_conflict").fetchone()[0]
                == 2
            )
        finally:
            connection.close()

    asyncio.run(run())


def test_capture_api_returns_per_event_results() -> None:
    event = _event()
    response = TestClient(create_app()).post(
        "/v1/capture/events",
        json={
            "events": [
                {
                    "schema_version": event.schema_version,
                    "event_id": str(event.event_id),
                    "producer_id": event.producer_id,
                    "stream_id": event.stream_id,
                    "sequence": event.sequence,
                    "source": {
                        "kind": event.source_identity.source_kind,
                        "scope": event.source_identity.source_scope,
                        "session_key": event.source_identity.session_key,
                        "item_key": event.source_identity.source_item_key,
                        "revision": event.source_identity.source_revision,
                    },
                    "captured_at": event.captured_at.isoformat(),
                    "rule_version": event.rule_version,
                    "payload_hash": event.payload_hash,
                    "payload": dict(event.payload),
                }
            ]
        },
    )
    assert response.status_code == 202
    assert response.json()["results"][0]["status"] in {"accepted", "already_received"}
