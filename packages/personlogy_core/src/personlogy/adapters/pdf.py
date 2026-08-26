"""PDF validation and extraction adapter."""

from __future__ import annotations

import io
import json
import re

import pdfplumber

from personlogy.ports.ingestion import ParsedPdfBlock


class PdfParseError(ValueError):
    pass


class PdfPlumberParser:
    def validate(self, content: bytes) -> int:
        if not content.startswith(b"%PDF-"):
            raise PdfParseError("file header is not a PDF")
        try:
            with pdfplumber.open(io.BytesIO(content)) as document:
                page_count = len(document.pages)
                if page_count < 1:
                    raise PdfParseError("PDF has no pages")
                for page in document.pages:
                    page.extract_text()
                return page_count
        except PdfParseError:
            raise
        except Exception as error:
            raise PdfParseError("PDF is corrupt or cannot be parsed") from error

    def parse(self, content: bytes) -> tuple[ParsedPdfBlock, ...]:
        self.validate(content)
        blocks: list[ParsedPdfBlock] = []
        with pdfplumber.open(io.BytesIO(content)) as document:
            for page_number, page in enumerate(document.pages, start=1):
                page_text = page.extract_text() or ""
                paragraphs = _paragraphs(page_text)
                for paragraph_index, paragraph in enumerate(paragraphs):
                    blocks.append(
                        ParsedPdfBlock(
                            content=paragraph,
                            locator={
                                "page": page_number,
                                "paragraph": paragraph_index,
                                "block_type": "heading"
                                if _looks_like_heading(paragraph, paragraph_index == 0)
                                else "paragraph",
                            },
                        )
                    )
                for table_index, table in enumerate(page.extract_tables() or []):
                    table_rows = [
                        [cell or "" for cell in row]
                        for row in table
                        if any(cell and cell.strip() for cell in row)
                    ]
                    if not table_rows:
                        continue
                    blocks.append(
                        ParsedPdfBlock(
                            content=json.dumps(table_rows, ensure_ascii=False),
                            locator={
                                "page": page_number,
                                "table": table_index,
                                "block_type": "table",
                            },
                        )
                    )
        return tuple(blocks)


def _paragraphs(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]


def _looks_like_heading(text: str, first_paragraph: bool) -> bool:
    first_line = text.splitlines()[0].strip()
    return first_paragraph and len(first_line) <= 120 and len(text.splitlines()) <= 3
