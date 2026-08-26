import asyncio
import os

import structlog

from personlogy.adapters.sqlite import SQLiteJobQueue, SQLiteStore, SQLiteUnitOfWorkFactory
from personlogy.application.orchestration import JobService


async def run_worker() -> None:
    database_path = os.getenv("PKS_SQLITE_PATH", "../../data/personlogy.sqlite3")
    store = SQLiteStore(database_path)
    queue = SQLiteJobQueue(store)
    service = JobService(SQLiteUnitOfWorkFactory(store), queue)
    logger = structlog.get_logger()
    logger.info("worker_started", queue_backend="sqlite", storage_path=database_path)
    while True:
        job = await service.start_next(timeout_seconds=2.0)
        if job is None:
            continue
        logger.info("job_claimed", job_id=str(job.id), kind=job.kind, attempt=job.attempt)
        try:
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
