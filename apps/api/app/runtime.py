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

store: SQLiteStore | InMemoryStore
uow_factory: UnitOfWorkFactory
if settings.storage_backend == "sqlite":
    store = SQLiteStore(settings.sqlite_path)
    uow_factory = SQLiteUnitOfWorkFactory(store)
elif settings.storage_backend == "memory":
    store = InMemoryStore()
    uow_factory = cast(UnitOfWorkFactory, InMemoryUnitOfWorkFactory(store))
else:
    raise RuntimeError("GEL storage backend is not available until the GEL adapter is implemented")

queue: JobQueue
if settings.queue_backend == "sqlite":
    if not isinstance(store, SQLiteStore):
        raise RuntimeError("sqlite queue requires sqlite storage_backend")
    queue = SQLiteJobQueue(store)
elif settings.queue_backend == "memory":
    queue = InMemoryJobQueue()
else:
    raise RuntimeError("GEL queue backend is not available until the GEL adapter is implemented")

job_service = JobService(uow_factory, queue)
conversation_import_service = ConversationImportService(uow_factory, job_service)
pdf_import_service = PdfImportService(
    uow_factory,
    job_service,
    LocalFileStorage(settings.pdf_storage_root),
    PdfPlumberParser(),
    max_size_bytes=settings.pdf_max_size_bytes,
)
