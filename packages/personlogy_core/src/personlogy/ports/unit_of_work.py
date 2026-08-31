from types import TracebackType
from typing import Protocol, Self

from personlogy.ports.repositories import (
    GovernanceRepository,
    JobRepository,
    KnowledgeRepository,
    SourceRepository,
)
from personlogy.ports.writeback import WritebackRepository


class UnitOfWork(Protocol):
    sources: SourceRepository
    knowledge: KnowledgeRepository
    governance: GovernanceRepository
    writebacks: WritebackRepository
    jobs: JobRepository

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


class UnitOfWorkFactory(Protocol):
    def __call__(self) -> UnitOfWork: ...
