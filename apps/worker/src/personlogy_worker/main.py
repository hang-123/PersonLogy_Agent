import asyncio
import os

import structlog
from personlogy.adapters.local_files import LocalFileStorage
from personlogy.adapters.pdf import PdfPlumberParser
from personlogy.adapters.sqlite import (
    SQLiteJobQueue,
    SQLiteStore,
    SQLiteUnitOfWorkFactory,
)
from personlogy.application.ingestion import PdfImportService
from personlogy.application.orchestration import JobService


async def run_worker() -> None:
    database_path = os.getenv("PKS_SQLITE_PATH", "../../data/personlogy.sqlite3")
    store = SQLiteStore(database_path)
    queue = SQLiteJobQueue(store)
    service = JobService(SQLiteUnitOfWorkFactory(store), queue)
    pdf_service = PdfImportService(
        SQLiteUnitOfWorkFactory(store),
        service,
        LocalFileStorage(os.getenv("PKS_PDF_STORAGE_ROOT", "../../data/files")),
        PdfPlumberParser(),
        max_size_bytes=int(os.getenv("PKS_PDF_MAX_SIZE_BYTES", str(25 * 1024 * 1024))),
    )
    logger = structlog.get_logger()
    logger.info("worker_started", queue_backend="sqlite", storage_path=database_path)
    while True:
        job = await service.start_next(timeout_seconds=2.0)
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
