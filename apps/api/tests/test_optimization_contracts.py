import asyncio
import json
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from personlogy.adapters.llm_openai import OpenAICompatCompiler
from personlogy.adapters.sqlite import SQLiteStore, SQLiteUnitOfWorkFactory
from personlogy.application.compilation import CompilationService, DocumentHeuristicCompiler
from personlogy.domain.job import Job
from personlogy.domain.source.models import ContentBlock
from personlogy.shared.errors import DomainValidationError


def test_citations_match_original_case_and_unicode_offsets() -> None:
    block = ContentBlock(uuid4(), 0, "İ prefix Gel is a database.", "hash", {"page": 1})
    payload = {
        "nodes": [{"title": "Gel"}],
        "claims": [
            {"subject_title": "Gel", "statement": "database", "quote": "gel is a database."},
            {"subject_title": "Gel", "statement": "database", "quote": "Gel is a database."},
        ],
        "relations": [],
    }
    compiler = OpenAICompatCompiler(
        base_url="https://example.test/v1",
        api_key="",
        model="test",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200, json={"choices": [{"message": {"content": json.dumps(payload)}}]}
            )
        ),
    )
    bundle = compiler.compile(project_id=uuid4(), blocks=(block,))
    assert len(bundle.claims) == 1
    citation = bundle.citations[0]
    start, end = citation.metadata["quote_start"], citation.metadata["quote_end"]
    assert block.content[start:end] == citation.quote
    assert bundle.okf["citations"][0]["metadata"]["quote_start"] == start


def test_compilation_boundary_rejects_fabricated_quote() -> None:
    project_id = uuid4()
    block = ContentBlock(uuid4(), 0, "Source evidence.", "hash", {"page": 1})
    bundle = DocumentHeuristicCompiler().compile(project_id=project_id, blocks=(block,))
    fake = replace(bundle.citations[0], quote="Fabricated evidence.")
    bundle = replace(
        bundle, citations=(fake,), claims=(replace(bundle.claims[0], citations=(fake,)),)
    )
    with pytest.raises(DomainValidationError, match="quote"):
        CompilationService._validate_bundle(bundle, project_id, (block,))


def test_heuristic_quotes_preserve_whitespace_and_truncate_without_ellipsis() -> None:
    project_id = uuid4()
    block = ContentBlock(uuid4(), 0, "Heading\n\n" + "source  evidence " * 100, "hash", {"page": 1})
    bundle = DocumentHeuristicCompiler().compile(project_id=project_id, blocks=(block,))
    CompilationService._validate_bundle(bundle, project_id, (block,))
    assert all(citation.quote in block.content for citation in bundle.citations)


def test_sqlite_job_filter_is_applied_before_limit(tmp_path: Path) -> None:
    async def run() -> None:
        factory = SQLiteUnitOfWorkFactory(SQLiteStore(tmp_path / "jobs.sqlite3"))
        project_id = uuid4()
        wanted = Job("test", "wanted", {"project_id": str(project_id)})
        async with factory() as uow:
            await uow.jobs.add(wanted)
            await uow.jobs.add(Job("test", "other", {"project_id": str(uuid4())}))
            await uow.commit()
        async with factory() as uow:
            assert await uow.jobs.list(project_id=project_id, limit=1) == [wanted]

    asyncio.run(run())
