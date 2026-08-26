import asyncio

import structlog

from personlogy.adapters.memory import InMemoryJobQueue, InMemoryStore, InMemoryUnitOfWorkFactory
from personlogy.application.orchestration import JobService


async def run_worker() -> None:
    queue = InMemoryJobQueue()
    service = JobService(InMemoryUnitOfWorkFactory(InMemoryStore()), queue)
    structlog.get_logger().info("worker_started", queue_backend="memory")
    while True:
        job = await service.start_next(timeout_seconds=2.0)
        if job is None:
            continue


def main() -> None:
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        structlog.get_logger().info("worker_stopped")


if __name__ == "__main__":
    main()
