import asyncio
from pathlib import Path
from uuid import uuid4

from personlogy.adapters.sqlite_lineage import SQLiteLineageStore
from personlogy.application.lineage import LineageService, add_lineage_link
from personlogy.domain.lineage import LineageLink


def test_lineage_store_is_idempotent_and_traverses_connected_component(tmp_path: Path) -> None:
    asyncio.run(_test_lineage_store_is_idempotent_and_traverses_connected_component(tmp_path))


async def _test_lineage_store_is_idempotent_and_traverses_connected_component(
    tmp_path: Path,
) -> None:
    store = SQLiteLineageStore(tmp_path / "personlogy.sqlite3")
    project_id = uuid4()
    source_version_id = uuid4()
    content_block_id = uuid4()
    citation_id = uuid4()
    claim_id = uuid4()
    job_id = uuid4()
    request_id = "retrieval-request-1"

    links = [
        LineageLink(
            project_id,
            "source_version",
            str(source_version_id),
            "parsed_as",
            "content_block",
            str(content_block_id),
        ),
        LineageLink(
            project_id,
            "content_block",
            str(content_block_id),
            "extracted_as",
            "citation",
            str(citation_id),
        ),
        LineageLink(
            project_id,
            "claim",
            str(claim_id),
            "supported_by",
            "citation",
            str(citation_id),
        ),
        LineageLink(
            project_id,
            "job",
            str(job_id),
            "input",
            "source_version",
            str(source_version_id),
        ),
        LineageLink(
            project_id,
            "retrieval_request",
            request_id,
            "returned_claim",
            "claim",
            str(claim_id),
        ),
    ]
    stored = [await store.add_link(link) for link in links]
    duplicate = await store.add_link(links[0])

    assert duplicate.link_id == stored[0].link_id
    claim_trace = await LineageService(store).trace_claim(
        project_id=project_id,
        claim_id=claim_id,
    )
    assert len(claim_trace.links) == len(links)
    assert {link.to_type for link in claim_trace.links} >= {
        "citation",
        "content_block",
        "source_version",
    }
    job_trace = await LineageService(store).trace_job(project_id=project_id, job_id=job_id)
    assert any(link.to_id == str(source_version_id) for link in job_trace.links)
    retrieval_trace = await LineageService(store).trace_retrieval(
        project_id=project_id,
        request_id=request_id,
    )
    assert any(link.to_id == str(claim_id) for link in retrieval_trace.links)

    other_project = uuid4()
    await add_lineage_link(
        store,
        project_id=other_project,
        from_type="claim",
        from_id=claim_id,
        relation_type="isolated",
        to_type="source_version",
        to_id=source_version_id,
    )
    isolated_trace = await LineageService(store).trace_claim(
        project_id=project_id,
        claim_id=claim_id,
    )
    assert all(link.project_id == project_id for link in isolated_trace.links)
    assert len(isolated_trace.links) == len(links)
