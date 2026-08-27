import asyncio
import os

import structlog
from personlogy.adapters.local_files import LocalFileStorage
from personlogy.adapters.pdf import PdfPlumberParser
from personlogy.adapters.sqlite import SQLiteJobQueue, SQLiteStore, SQLiteUnitOfWorkFactory
from personlogy.application.ingestion import PdfImportService
from personlogy.application.orchestration import JobService
from personlogy.ports.queue import JobQueue
from personlogy.ports.unit_of_work import UnitOfWorkFactory

STORAGE_BACKEND = os.getenv("PKS_STORAGE_BACKEND", "sqlite")
QUEUE_BACKEND = os.getenv("PKS_QUEUE_BACKEND", STORAGE_BACKEND)
PDF_STORAGE_ROOT = os.getenv("PKS_PDF_STORAGE_ROOT", "../../data/files")
PDF_MAX_SIZE_BYTES = int(os.getenv("PKS_PDF_MAX_SIZE_BYTES", str(25 * 1024 * 1024)))
POLL_INTERVAL = float(os.getenv("PKS_QUEUE_POLL_INTERVAL_SECONDS", "2.0"))


def _build_services() -> tuple[UnitOfWorkFactory, JobQueue]:
    if STORAGE_BACKEND == "gel":
        from personlogy.adapters.gel import GelJobQueue, GelStore, GelUnitOfWorkFactory

        dsn = os.getenv("PKS_GEL_DSN")
        if not dsn:
            raise RuntimeError("PKS_GEL_DSN is required when storage_backend is gel")
        store = GelStore(dsn)
        factory: UnitOfWorkFactory = GelUnitOfWorkFactory(store)
        queue: JobQueue = GelJobQueue(store)
        return factory, queue
    if STORAGE_BACKEND == "sqlite":
        sqlite_store = SQLiteStore(os.getenv("PKS_SQLITE_PATH", "../../data/personlogy.sqlite3"))
        sqlite_factory = SQLiteUnitOfWorkFactory(sqlite_store)
        if QUEUE_BACKEND == "sqlite":
            return sqlite_factory, SQLiteJobQueue(sqlite_store)
        raise RuntimeError(f"unsupported queue_backend for sqlite storage: {QUEUE_BACKEND}")
    raise RuntimeError(f"unsupported storage_backend: {STORAGE_BACKEND}")


async def run_worker() -> None:
    uow_factory, queue = _build_services()
    service = JobService(uow_factory, queue)
    pdf_service = PdfImportService(
        uow_factory,
        service,
        LocalFileStorage(PDF_STORAGE_ROOT),
        PdfPlumberParser(),
        max_size_bytes=PDF_MAX_SIZE_BYTES,
    )
    logger = structlog.get_logger()
    logger.info(
        "worker_started",
        storage_backend=STORAGE_BACKEND,
        queue_backend=QUEUE_BACKEND,
    )
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
            else:
                await service.report_progress(job.id, 10, "accepted")
            await service.succeed(job.id)
        except Exception as error:
            logger.exception("job_failed", job_id=str(job.id), error=str(error))
            await service.fail(job.id, str(error), retryable=True)


def main() -> None:
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        structlog.get_logger().info("worker_stopped")


if __name__ == "__main__":
    main()
