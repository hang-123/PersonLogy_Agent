from collections.abc import Awaitable, Callable
from typing import cast

from personlogy.adapters.local_files import LocalFileStorage
from personlogy.adapters.memory import InMemoryJobQueue, InMemoryStore, InMemoryUnitOfWorkFactory
from personlogy.adapters.pdf import PdfPlumberParser
from personlogy.adapters.sqlite import SQLiteJobQueue, SQLiteStore, SQLiteUnitOfWorkFactory
from personlogy.application.ingestion import ConversationImportService, PdfImportService
from personlogy.application.orchestration import JobService
from personlogy.ports.queue import JobQueue
from personlogy.ports.unit_of_work import UnitOfWorkFactory

from app.core.config import get_settings

settings = get_settings()

gel_store: "GelStore | None" = None

store: SQLiteStore | InMemoryStore | None = None
uow_factory: UnitOfWorkFactory
if settings.storage_backend == "sqlite":
    store = SQLiteStore(settings.sqlite_path)
    uow_factory = SQLiteUnitOfWorkFactory(store)
elif settings.storage_backend == "memory":
    store = InMemoryStore()
    uow_factory = cast(UnitOfWorkFactory, InMemoryUnitOfWorkFactory(store))
elif settings.storage_backend == "gel":
    from personlogy.adapters.gel import GelStore, GelUnitOfWorkFactory

    if not settings.gel_dsn:
        raise RuntimeError("PKS_GEL_DSN is required when storage_backend is gel")
    gel_store = GelStore(settings.gel_dsn)
    uow_factory = GelUnitOfWorkFactory(gel_store)
else:  # pragma: no cover - guarded by Settings Literal
    raise RuntimeError(f"unsupported storage_backend: {settings.storage_backend}")

queue: JobQueue
if settings.queue_backend == "sqlite":
    if not isinstance(store, SQLiteStore):
        raise RuntimeError("sqlite queue requires sqlite storage_backend")
    queue = SQLiteJobQueue(store)
elif settings.queue_backend == "memory":
    queue = InMemoryJobQueue()
elif settings.queue_backend == "gel":
    from personlogy.adapters.gel import GelJobQueue

    if gel_store is None:
        raise RuntimeError("gel queue requires gel storage_backend")
    queue = GelJobQueue(gel_store)
else:  # pragma: no cover - guarded by Settings Literal
    raise RuntimeError(f"unsupported queue_backend: {settings.queue_backend}")

job_service = JobService(uow_factory, queue)
conversation_import_service = ConversationImportService(uow_factory, job_service)
pdf_import_service = PdfImportService(
    uow_factory,
    job_service,
    LocalFileStorage(settings.pdf_storage_root),
    PdfPlumberParser(),
    max_size_bytes=settings.pdf_max_size_bytes,
)

_shutdown_hooks: list[Callable[[], Awaitable[None]]] = []
if gel_store is not None:
    _shutdown_hooks.append(gel_store.aclose)


async def shutdown() -> None:
    for hook in _shutdown_hooks:
        await hook()
