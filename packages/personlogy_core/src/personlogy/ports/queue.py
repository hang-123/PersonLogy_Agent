from typing import Protocol
from uuid import UUID


class JobQueue(Protocol):
    async def enqueue(self, job_id: UUID) -> None: ...

    async def dequeue(self, *, timeout_seconds: float | None = None) -> UUID | None: ...
