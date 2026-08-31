from uuid import UUID

from fastapi import APIRouter, HTTPException, Response, status

from app.modules.sources.schemas import (
    ContentBlockResponse,
    EvidenceDetailResponse,
    SourceVersionResponse,
    SourceVersionSummaryResponse,
)
from app.runtime import source_read_service

router = APIRouter(tags=["sources"])


def _block_response(block) -> ContentBlockResponse:  # type: ignore[no-untyped-def]
    return ContentBlockResponse(
        id=block.id,
        source_version_id=block.source_version_id,
        ordinal=block.ordinal,
        content=block.content,
        content_hash=block.content_hash,
        locator=block.locator,
    )


def _version_summary(version, *, content_available: bool) -> SourceVersionSummaryResponse:  # type: ignore[no-untyped-def]
    return SourceVersionSummaryResponse(
        id=version.id,
        source_id=version.source_id,
        version=version.version,
        content_hash=version.content_hash,
        created_at=version.created_at,
        content_available=content_available,
    )


@router.get(
    "/source-versions/{source_version_id}",
    response_model=SourceVersionResponse,
)
async def get_source_version(source_version_id: UUID, project_id: UUID) -> SourceVersionResponse:
    detail = await source_read_service.get_source_version(source_version_id, project_id=project_id)
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="source version not found"
        )
    return SourceVersionResponse(
        id=detail.version.id,
        source_id=detail.version.source_id,
        version=detail.version.version,
        content_hash=detail.version.content_hash,
        created_at=detail.version.created_at,
        content_available=True,
        blocks=[_block_response(block) for block in detail.blocks],
    )


@router.get("/evidence/{evidence_id}", response_model=EvidenceDetailResponse)
async def get_evidence(evidence_id: UUID, project_id: UUID) -> EvidenceDetailResponse:
    detail = await source_read_service.get_evidence(evidence_id, project_id=project_id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="evidence not found")
    return EvidenceDetailResponse(
        id=detail.citation.id,
        quote=detail.citation.quote,
        locator=detail.citation.locator,
        metadata=detail.citation.metadata,
        content_block=_block_response(detail.block),
        source_version=_version_summary(detail.version, content_available=True),
    )


@router.get("/source-versions/{source_version_id}/content")
async def read_source_content(source_version_id: UUID, project_id: UUID) -> Response:
    try:
        result = await source_read_service.read_source_content(
            source_version_id, project_id=project_id
        )
    except FileNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="source content is not available",
        ) from error
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="source content not found"
        )
    version, content = result
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{version.id}.pdf"'},
    )
