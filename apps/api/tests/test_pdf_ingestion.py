import asyncio
from pathlib import Path

import pytest
from personlogy.adapters.local_files import LocalFileStorage
from personlogy.adapters.pdf import PdfPlumberParser
from personlogy.adapters.sqlite import SQLiteJobQueue, SQLiteStore, SQLiteUnitOfWorkFactory
from personlogy.application.ingestion import PdfImportService, PdfUploadError
from personlogy.application.orchestration import JobService


def test_pdf_import_persists_file_version_and_blocks(tmp_path: Path) -> None:
    asyncio.run(_test_pdf_import_persists_file_version_and_blocks(tmp_path))


async def _test_pdf_import_persists_file_version_and_blocks(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "personlogy.sqlite3")
    factory = SQLiteUnitOfWorkFactory(store)
    service = PdfImportService(
        factory,
        JobService(factory, SQLiteJobQueue(store, poll_interval_seconds=0.01)),
        LocalFileStorage(tmp_path / "files"),
        PdfPlumberParser(),
        max_size_bytes=1024 * 1024,
    )
    content = _sample_pdf()

    first = await service.import_pdf(
        project_name="PDF 测试",
        project_slug="pdf-test",
        title="示例文档",
        filename="sample.pdf",
        content_type="application/pdf",
        content=content,
    )
    block_count = await service.process_pdf_job(first.job)
    second = await service.import_pdf(
        project_name="PDF 测试",
        project_slug="pdf-test",
        title="示例文档",
        filename="sample.pdf",
        content_type="application/pdf",
        content=content,
    )

    assert first.page_count == 1
    assert block_count == 1
    assert first.reused_version is False
    assert second.reused_version is True
    assert second.source_version_id == first.source_version_id
    assert second.job.id == first.job.id

    async with factory() as uow:
        blocks = await uow.sources.list_blocks(first.source_version_id)
    assert blocks[0].content == "Hello PDF"
    assert blocks[0].locator == {"page": 1, "paragraph": 0, "block_type": "heading"}
    assert (tmp_path / "files" / first.object_key).is_file()


def test_pdf_upload_rejects_invalid_input_without_creating_project(tmp_path: Path) -> None:
    asyncio.run(_test_pdf_upload_rejects_invalid_input_without_creating_project(tmp_path))


async def _test_pdf_upload_rejects_invalid_input_without_creating_project(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "personlogy.sqlite3")
    factory = SQLiteUnitOfWorkFactory(store)
    service = PdfImportService(
        factory,
        JobService(factory, SQLiteJobQueue(store, poll_interval_seconds=0.01)),
        LocalFileStorage(tmp_path / "files"),
        PdfPlumberParser(),
        max_size_bytes=32,
    )

    with pytest.raises(PdfUploadError, match="maximum size"):
        await service.import_pdf(
            project_name="不会创建",
            project_slug="invalid-pdf",
            title="超限",
            filename="too-large.pdf",
            content_type="application/pdf",
            content=b"%PDF-1.4" + b"x" * 32,
        )

    with pytest.raises(PdfUploadError, match="corrupt"):
        await service.import_pdf(
            project_name="不会创建",
            project_slug="invalid-pdf",
            title="损坏",
            filename="broken.pdf",
            content_type="application/pdf",
            content=b"%PDF-1.4\nnot a complete PDF",
        )

    async with factory() as uow:
        assert await uow.sources.get_project_by_slug("invalid-pdf") is None


def _sample_pdf() -> bytes:
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 300] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length 41 >>\nstream\nBT /F1 12 Tf 50 250 Td (Hello PDF) Tj ET\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    data = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, body in enumerate(objects, start=1):
        offsets.append(len(data))
        data.extend(f"{index} 0 obj\n".encode())
        data.extend(body)
        data.extend(b"\nendobj\n")
    xref = len(data)
    data.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    data.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        data.extend(f"{offset:010d} 00000 n \n".encode())
    data.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref}\n%%EOF\n".encode()
    )
    return bytes(data)
