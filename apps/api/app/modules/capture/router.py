from fastapi import APIRouter, status

from app.modules.capture.schemas import (
    CaptureEventResultResponse,
    CaptureEventsRequest,
    CaptureEventsResponse,
)
from app.runtime import capture_ingestion_service
from personlogy.domain.capture.models import CapturedEvent, CaptureSourceIdentity

router = APIRouter(prefix="/capture", tags=["capture"])


@router.post(
    "/events",
    response_model=CaptureEventsResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def ingest_capture_events(request: CaptureEventsRequest) -> CaptureEventsResponse:
    receipt = await capture_ingestion_service.ingest(
        tuple(
            CapturedEvent(
                schema_version=event.schema_version,
                event_id=event.event_id,
                producer_id=event.producer_id,
                stream_id=event.stream_id,
                sequence=event.sequence,
                source_identity=CaptureSourceIdentity(
                    source_kind=event.source.kind,
                    source_scope=event.source.scope,
                    session_key=event.source.session_key,
                    source_item_key=event.source.item_key,
                    source_revision=event.source.revision,
                ),
                occurred_at=event.occurred_at,
                captured_at=event.captured_at,
                rule_version=event.rule_version,
                payload_hash=event.payload_hash,
                payload=event.payload,
            )
            for event in request.events
        )
    )
    return CaptureEventsResponse(
        receipt_id=str(receipt.receipt_id),
        results=[
            CaptureEventResultResponse(
                event_id=result.event_id,
                status=result.status,
                server_receipt_id=result.server_receipt_id,
                error_code=result.error_code,
                error_summary=result.error_summary,
            )
            for result in receipt.results
        ],
    )
