import asyncio
import os
from collections.abc import Awaitable
from typing import Any
from uuid import UUID

import structlog
from personlogy.adapters.local_files import LocalFileStorage
from personlogy.adapters.pdf import PdfPlumberParser
from personlogy.adapters.sqlite import SQLiteJobQueue, SQLiteStore, SQLiteUnitOfWorkFactory
from personlogy.adapters.sqlite_features import SQLiteFeatureStore, SQLiteRetrievalIndexer
from personlogy.application.compilation import CompilationService, DocumentHeuristicCompiler
from personlogy.application.ingestion import PdfImportService
from personlogy.application.orchestration import JobService
from personlogy.ports.queue import JobQueue
from personlogy.ports.unit_of_work import UnitOfWorkFactory

STORAGE_BACKEND = os.getenv("PKS_STORAGE_BACKEND", "sqlite")
QUEUE_BACKEND = os.getenv("PKS_QUEUE_BACKEND", STORAGE_BACKEND)
PDF_STORAGE_ROOT = os.getenv("PKS_PDF_STORAGE_ROOT", "../../data/files")
PDF_MAX_SIZE_BYTES = int(os.getenv("PKS_PDF_MAX_SIZE_BYTES", str(25 * 1024 * 1024)))
POLL_INTERVAL = float(os.getenv("PKS_QUEUE_POLL_INTERVAL_SECONDS", "2.0"))


def _build_services() -> tuple[
    UnitOfWorkFactory, JobQueue, Any | None, SQLiteRetrievalIndexer | None
]:
    """Return (uow_factory, queue, store_to_close, retrieval_indexer)."""
    if STORAGE_BACKEND == "gel":
        from personlogy.adapters.gel import GelJobQueue, GelStore, GelUnitOfWorkFactory

        dsn = os.getenv("PKS_GEL_DSN")
        if not dsn:
            raise RuntimeError("PKS_GEL_DSN is required when storage_backend is gel")
        store = GelStore(dsn)
        factory: UnitOfWorkFactory = GelUnitOfWorkFactory(store)
        queue: JobQueue = GelJobQueue(store)
        return factory, queue, store, None
    if STORAGE_BACKEND == "sqlite":
        sqlite_store = SQLiteStore(os.getenv("PKS_SQLITE_PATH", "../../data/personlogy.sqlite3"))
        sqlite_factory = SQLiteUnitOfWorkFactory(sqlite_store)
        if QUEUE_BACKEND == "sqlite":
            feature_store = SQLiteFeatureStore(sqlite_store.path)
            return (
                sqlite_factory,
                SQLiteJobQueue(sqlite_store),
                None,
                SQLiteRetrievalIndexer(feature_store),
            )
        raise RuntimeError(f"unsupported queue_backend for sqlite storage: {QUEUE_BACKEND}")
    raise RuntimeError(f"unsupported storage_backend: {STORAGE_BACKEND}")


async def run_worker() -> None:
    uow_factory, queue, store, retrieval_indexer = _build_services()
    if store is not None:
        aclose: Awaitable[None] = store.aclose()
    else:
        aclose = _noop()
    service = JobService(uow_factory, queue)
    pdf_service = PdfImportService(
        uow_factory,
        service,
        LocalFileStorage(PDF_STORAGE_ROOT),
        PdfPlumberParser(),
        max_size_bytes=PDF_MAX_SIZE_BYTES,
    )
    compilation_service = CompilationService(
        uow_factory,
        service,
        DocumentHeuristicCompiler(),
        LocalFileStorage(PDF_STORAGE_ROOT),
    )
    logger = structlog.get_logger()
    logger.info(
        "worker_started",
        storage_backend=STORAGE_BACKEND,
        queue_backend=QUEUE_BACKEND,
    )
    try:
        while True:
            job = await service.start_next(timeout_seconds=POLL_INTERVAL)
            if job is None:
                continue
            logger.info("job_claimed", job_id=str(job.id), kind=job.kind, attempt=job.attempt)
            try:
                if job.kind == "pdf.parse":
                    await service.report_progress(job.id, 20, "parsing")
                    block_count = await pdf_service.process_pdf_job(job)
                    await service.report_progress(
                        job.id, 90, f"content_blocks_written:{block_count}"
                    )
                    await compilation_service.submit_for_version(
                        project_id=UUID(str(job.payload["project_id"])),
                        source_version_id=UUID(str(job.payload["source_version_id"])),
                    )
                elif job.kind == "knowledge.compile":
                    await service.report_progress(job.id, 20, "compiling_candidates")
                    result = await compilation_service.process_compile_job(job)
                    await service.report_progress(
                        job.id,
                        90,
                        f"governance:{result.governance_status}:review_tasks:{result.review_task_count}",
                    )
                elif job.kind == "retrieval.index":
                    if retrieval_indexer is None:
                        raise RuntimeError("SQLite retrieval indexer is not configured")
                    await service.report_progress(job.id, 20, "rebuilding_retrieval_index")
                    project_id = UUID(str(job.payload["project_id"]))
                    count = await retrieval_indexer.rebuild_project(project_id)
                    await service.report_progress(
                        job.id, 90, f"retrieval_documents_indexed:{count}"
                    )
                else:
                    await service.report_progress(job.id, 10, "accepted")
                await service.succeed(job.id)
            except Exception as error:
                logger.exception("job_failed", job_id=str(job.id), error=str(error))
                await service.fail(job.id, str(error), retryable=True)
    finally:
        await aclose


async def _noop() -> None:
    return None


def main() -> None:
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        structlog.get_logger().info("worker_stopped")


if __name__ == "__main__":
    main()
