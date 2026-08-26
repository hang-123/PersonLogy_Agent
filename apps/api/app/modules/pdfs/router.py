from typing import Annotated

from fastapi import APIRouter, File, Form, UploadFile, status

from app.core.config import get_settings
from app.modules.pdfs.schemas import PdfImportResponse
from app.runtime import pdf_import_service

router = APIRouter(prefix="/pdfs", tags=["pdfs"])


@router.post(
    "/upload",
    response_model=PdfImportResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_pdf(
    project_name: Annotated[str, Form(min_length=1, max_length=255)],
    project_slug: Annotated[str, Form(min_length=1, max_length=100)],
    title: Annotated[str, Form(min_length=1, max_length=255)],
    file: Annotated[UploadFile, File()],
) -> PdfImportResponse:
    settings = get_settings()
    content = await file.read(settings.pdf_max_size_bytes + 1)
    result = await pdf_import_service.import_pdf(
        project_name=project_name,
        project_slug=project_slug,
        title=title,
        filename=file.filename or "upload.pdf",
        content_type=file.content_type,
        content=content,
    )
    return PdfImportResponse(
        project_id=result.project_id,
        source_id=result.source_id,
        source_version_id=result.source_version_id,
        version=result.version,
        content_hash=result.content_hash,
        object_key=result.object_key,
        page_count=result.page_count,
        job_id=result.job.id,
        reused_version=result.reused_version,
    )
