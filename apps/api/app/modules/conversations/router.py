from fastapi import APIRouter, status
from personlogy.application.ingestion import IncomingConversationMessage

from app.modules.conversations.schemas import (
    ConversationImportRequest,
    ConversationImportResponse,
)
from app.runtime import conversation_import_service

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.post(
    "/import",
    response_model=ConversationImportResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def import_conversation(
    request: ConversationImportRequest,
) -> ConversationImportResponse:
    result = await conversation_import_service.import_conversation(
        project_name=request.project_name,
        project_slug=request.project_slug,
        conversation_external_id=request.conversation_id,
        title=request.title,
        messages=tuple(
            IncomingConversationMessage(
                external_id=message.message_id,
                role=message.role,
                content=message.content,
                ordinal=message.ordinal,
                created_at=message.created_at,
                parent_external_id=message.parent_message_id,
                attachments=tuple(dict(item) for item in message.attachments),
            )
            for message in request.messages
        ),
        metadata=dict(request.metadata),
    )
    return ConversationImportResponse(
        project_id=result.project_id,
        source_id=result.source_id,
        conversation_id=result.conversation_id,
        job_id=result.job.id,
        imported_message_count=result.imported_message_count,
        duplicate_message_count=result.duplicate_message_count,
    )
