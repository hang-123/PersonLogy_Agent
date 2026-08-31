from collections.abc import Awaitable, Callable
from typing import cast
from uuid import UUID

from personlogy.adapters.gel_audit import GelAuditStore
from personlogy.adapters.llm_openai import (
    OpenAICompatCompiler,
    OpenAICompatEmbeddingProvider,
    OpenAICompatReranker,
)
from personlogy.adapters.local_files import LocalFileStorage
from personlogy.adapters.memory import InMemoryJobQueue, InMemoryStore, InMemoryUnitOfWorkFactory
from personlogy.adapters.pdf import PdfPlumberParser
from personlogy.adapters.sqlite import SQLiteJobQueue, SQLiteStore, SQLiteUnitOfWorkFactory
from personlogy.adapters.sqlite_audit import SQLiteRecordStore
from personlogy.adapters.sqlite_features import (
    SQLiteFeatureStore,
    SQLiteRetrievalIndexer,
    SQLiteRetrievalReader,
    SQLiteSchemaRegistry,
)
from personlogy.adapters.sqlite_lineage import SQLiteLineageStore
from personlogy.adapters.sqlite_metrics import SQLiteMetricsStore
from personlogy.adapters.sqlite_replay import SQLiteReplayStore
from personlogy.application.compilation import CompilationService, DocumentHeuristicCompiler
from personlogy.application.governance import GovernanceService
from personlogy.application.ingestion import ConversationImportService, PdfImportService
from personlogy.application.lineage import LineageService
from personlogy.application.monitoring import MetricsProjector, MonitoringService
from personlogy.application.orchestration import JobService, StageRunner
from personlogy.application.replay import ReplayService
from personlogy.application.retrieval import RetrievalService
from personlogy.application.schema_management import SchemaChangeService
from personlogy.application.source_read import SourceReadService
from personlogy.application.writeback import (
    LocalWritebackAuthorizer,
    RegistrySchemaWritebackValidator,
    WritebackService,
)
from personlogy.ports.audit import AuditSink
from personlogy.ports.compilation import KnowledgeCompiler
from personlogy.ports.lineage import LineageStore
from personlogy.ports.queue import JobQueue
from personlogy.ports.retrieval import (
    EmbeddingProvider,
    Reranker,
    RetrievalHit,
    RetrievalReader,
)
from personlogy.ports.unit_of_work import UnitOfWorkFactory

from app.core.config import get_settings

CompilationServiceCompiler = KnowledgeCompiler

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

audit_sink: AuditSink | None = None
lineage_store: LineageStore | None = None
if isinstance(store, SQLiteStore):
    audit_sink = SQLiteRecordStore(store.path)
    lineage_store = SQLiteLineageStore(store.path)
elif gel_store is not None:
    audit_sink = GelAuditStore(gel_store)

job_service = JobService(uow_factory, queue, audit_sink=audit_sink)
stage_runner = StageRunner(audit_sink)
conversation_import_service = ConversationImportService(uow_factory, job_service)
pdf_import_service = PdfImportService(
    uow_factory,
    job_service,
    LocalFileStorage(settings.pdf_storage_root),
    PdfPlumberParser(),
    max_size_bytes=settings.pdf_max_size_bytes,
    lineage_store=lineage_store,
)
source_read_service = SourceReadService(
    uow_factory,
    LocalFileStorage(settings.pdf_storage_root),
)
# LLM compiler: replace the deterministic heuristic with an OpenAI-compatible
# chat model when PKS_LLM_PROVIDER=openai_compatible and base_url/model are set.
if settings.llm_enabled():
    compiler: CompilationServiceCompiler = OpenAICompatCompiler(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
    )
else:
    compiler = DocumentHeuristicCompiler()
compilation_service = CompilationService(
    uow_factory,
    job_service,
    compiler,
    LocalFileStorage(settings.pdf_storage_root),
    lineage_store=lineage_store,
)
governance_service = GovernanceService(
    uow_factory, audit_sink=audit_sink, lineage_store=lineage_store
)
feature_store: SQLiteFeatureStore | None = None
schema_registry: SQLiteSchemaRegistry | None = None
if isinstance(store, SQLiteStore):
    feature_store = SQLiteFeatureStore(store.path)
    schema_registry = SQLiteSchemaRegistry(feature_store)
writeback_service = WritebackService(
    uow_factory,
    LocalFileStorage(settings.pdf_storage_root),
    authorizer=LocalWritebackAuthorizer(environment=settings.environment),
    schema_validator=(
        RegistrySchemaWritebackValidator(schema_registry) if schema_registry is not None else None
    ),
    audit_sink=audit_sink,
    lineage_store=lineage_store,
)
schema_service: SchemaChangeService | None = None


class _EmptyRetrievalReader:
    async def search(
        self,
        *,
        project_id: UUID,
        query: str,
        limit: int = 20,
        expand_relations: bool = False,
    ) -> tuple[RetrievalHit, ...]:
        return ()


retrieval_indexer: SQLiteRetrievalIndexer | None = None
# Optional OpenAI-compatible provider instances (see .env.example). The current
# retrieval pipeline is BM25-first (SQLite); embedding/rerank wiring for a true
# hybrid reader is the next step and is exposed here so services can consume them.
embedding_provider: EmbeddingProvider | None = None
reranker: Reranker | None = None
if settings.embedding_enabled():
    embedding_provider = cast(
        EmbeddingProvider,
        OpenAICompatEmbeddingProvider(
            base_url=settings.embedding_base_url,
            api_key=settings.embedding_api_key,
            model=settings.embedding_model,
        ),
    )
if settings.rerank_enabled():
    reranker = cast(
        Reranker,
        OpenAICompatReranker(
            base_url=settings.rerank_base_url,
            api_key=settings.rerank_api_key,
            model=settings.rerank_model,
        ),
    )
if isinstance(store, SQLiteStore):
    assert feature_store is not None
    assert schema_registry is not None
    schema_service = SchemaChangeService(
        schema_registry, audit_sink=audit_sink
    )
    retrieval_indexer = SQLiteRetrievalIndexer(
        feature_store, audit_sink=audit_sink, lineage_store=lineage_store
    )
    retrieval_reader: RetrievalReader = SQLiteRetrievalReader(feature_store)
else:
    retrieval_reader = _EmptyRetrievalReader()
retrieval_service = RetrievalService(
    retrieval_reader, audit_sink=audit_sink, lineage_store=lineage_store
)
lineage_service: LineageService | None = (
    LineageService(lineage_store) if lineage_store is not None else None
)
replay_store: SQLiteReplayStore | None = None
replay_service: ReplayService | None = None
if isinstance(store, SQLiteStore):
    replay_store = SQLiteReplayStore(store.path)
    replay_service = ReplayService(
        uow_factory,
        job_service,
        replay_store,
        audit_sink=audit_sink,
        lineage_store=lineage_store,
    )
metrics_store: SQLiteMetricsStore | None = None
monitoring_service: MonitoringService | None = None
if isinstance(store, SQLiteStore) and audit_sink is not None:
    metrics_store = SQLiteMetricsStore(store.path)
    metrics_projector = MetricsProjector(
        audit_sink,
        metrics_store,
        batch_size=settings.metrics_projector_batch_size,
    )
    monitoring_service = MonitoringService(
        metrics_projector,
        metrics_store,
        audit_sink,
        metrics_store,
        queue_degraded_threshold=settings.queue_backlog_degraded_threshold,
        index_stale_after_seconds=settings.index_stale_after_seconds,
    )

_shutdown_hooks: list[Callable[[], Awaitable[None]]] = []
if gel_store is not None:
    _shutdown_hooks.append(gel_store.aclose)


async def shutdown() -> None:
    for hook in _shutdown_hooks:
        await hook()
