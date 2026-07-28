import signal
from threading import Event

import structlog

from app.core.config import get_settings
from app.core.logging import configure_logging


def run() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    logger = structlog.get_logger()
    stopped = Event()

    def request_stop(signum: int, _frame: object) -> None:
        logger.info("worker_stop_requested", signal=signum)
        stopped.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    logger.info(
        "worker_started",
        environment=settings.environment,
        mode="idle_until_processing_job_repository_is_implemented",
    )
    stopped.wait()
    logger.info("worker_stopped")


if __name__ == "__main__":
    run()
