import asyncio

import structlog

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.runtime import job_service


async def run_worker() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    logger = structlog.get_logger()
    logger.info("worker_started", queue_backend=settings.queue_backend)
    while True:
        job = await job_service.start_next(timeout_seconds=settings.queue_poll_interval_seconds)
        if job is None:
            continue
        logger.info("job_claimed", job_id=str(job.id), kind=job.kind, attempt=job.attempt)
        try:
            await job_service.report_progress(job.id, 10, "accepted")
            await job_service.succeed(job.id)
        except Exception as error:
            logger.exception("job_failed", job_id=str(job.id), error=str(error))
            await job_service.fail(job.id, str(error), retryable=True)


def main() -> None:
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        structlog.get_logger().info("worker_stopped")


if __name__ == "__main__":
    main()
