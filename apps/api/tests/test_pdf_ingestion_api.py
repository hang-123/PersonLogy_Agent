from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import create_app


def test_pdf_upload_endpoint_returns_version_and_job() -> None:
    suffix = str(uuid4())
    response = TestClient(create_app()).post(
        "/v1/pdfs/upload",
        data={
            "project_name": "API PDF 测试",
            "project_slug": f"api-pdf-{suffix}",
            "title": "示例文档",
        },
        files={"file": ("sample.pdf", _sample_pdf(), "application/pdf")},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["version"] == 1
    assert body["page_count"] == 1
    assert body["reused_version"] is False
    assert body["job_id"]


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
