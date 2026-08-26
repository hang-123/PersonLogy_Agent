from personlogy.adapters.memory import (
    InMemoryJobQueue,
    InMemoryStore,
    InMemoryUnitOfWorkFactory,
)
from personlogy.application.orchestration import JobService

store = InMemoryStore()
queue = InMemoryJobQueue()
uow_factory = InMemoryUnitOfWorkFactory(store)
job_service = JobService(uow_factory, queue)  # type: ignore[arg-type]
