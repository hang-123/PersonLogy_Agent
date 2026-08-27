import asyncio
from dataclasses import dataclass, field
from types import TracebackType
from uuid import UUID

from personlogy.domain.governance.models import (
    ConflictRecord,
    DuplicateGroup,
    GovernanceIssue,
    GovernanceRun,
    ReviewTask,
)
from personlogy.domain.job import Job
from personlogy.domain.knowledge.models import Citation, Claim, KnowledgeNode
from personlogy.domain.relation.models import Relation, RelationType
from personlogy.domain.source.conversation import Conversation, ConversationMessage
from personlogy.domain.source.models import (
    ContentBlock,
    Project,
    Source,
    SourceKind,
    SourceVersion,
)
from personlogy.shared.errors import DomainValidationError


@dataclass(slots=True)
class InMemoryStore:
    projects: dict[UUID, Project] = field(default_factory=dict)
    sources: dict[UUID, Source] = field(default_factory=dict)
    versions: dict[UUID, SourceVersion] = field(default_factory=dict)
    blocks: dict[UUID, ContentBlock] = field(default_factory=dict)
    nodes: dict[UUID, KnowledgeNode] = field(default_factory=dict)
    citations: dict[UUID, Citation] = field(default_factory=dict)
    claims: dict[UUID, Claim] = field(default_factory=dict)
    relations: dict[UUID, Relation] = field(default_factory=dict)
    relation_types: dict[str, RelationType] = field(default_factory=dict)
    governance_runs: dict[UUID, GovernanceRun] = field(default_factory=dict)
    governance_issues: dict[UUID, GovernanceIssue] = field(default_factory=dict)
    duplicate_groups: dict[UUID, DuplicateGroup] = field(default_factory=dict)
    conflicts: dict[UUID, ConflictRecord] = field(default_factory=dict)
    review_tasks: dict[UUID, ReviewTask] = field(default_factory=dict)
    jobs: dict[UUID, Job] = field(default_factory=dict)
    conversations: dict[UUID, Conversation] = field(default_factory=dict)
    messages: dict[UUID, ConversationMessage] = field(default_factory=dict)

    def clone(self) -> "InMemoryStore":
        return InMemoryStore(
            projects=self.projects.copy(),
            sources=self.sources.copy(),
            versions=self.versions.copy(),
            blocks=self.blocks.copy(),
            nodes=self.nodes.copy(),
            citations=self.citations.copy(),
            claims=self.claims.copy(),
            relations=self.relations.copy(),
            relation_types=self.relation_types.copy(),
            governance_runs=self.governance_runs.copy(),
            governance_issues=self.governance_issues.copy(),
            duplicate_groups=self.duplicate_groups.copy(),
            conflicts=self.conflicts.copy(),
            review_tasks=self.review_tasks.copy(),
            jobs=self.jobs.copy(),
            conversations=self.conversations.copy(),
            messages=self.messages.copy(),
        )


class InMemorySourceRepository:
    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    async def add_project(self, project: Project) -> None:
        if any(item.slug == project.slug for item in self._store.projects.values()):
            raise DomainValidationError("project slug already exists")
        self._store.projects[project.id] = project

    async def get_project_by_slug(self, slug: str) -> Project | None:
        return next((item for item in self._store.projects.values() if item.slug == slug), None)

    async def add_conversation(self, conversation: Conversation) -> None:
        if (
            conversation.project_id not in self._store.projects
            or conversation.source_id not in self._store.sources
        ):
            raise DomainValidationError("conversation project or source does not exist")
        if any(
            item.project_id == conversation.project_id
            and item.external_id == conversation.external_id
            for item in self._store.conversations.values()
        ):
            raise DomainValidationError("conversation id already exists")
        self._store.conversations[conversation.id] = conversation

    async def get_conversation(
        self, project_id: UUID, external_id: str
    ) -> Conversation | None:
        return next(
            (
                item
                for item in self._store.conversations.values()
                if item.project_id == project_id and item.external_id == external_id
            ),
            None,
        )

    async def add_message(self, message: ConversationMessage) -> None:
        if message.conversation_id not in self._store.conversations:
            raise DomainValidationError("conversation does not exist")
        if any(
            item.conversation_id == message.conversation_id
            and item.external_id == message.external_id
            for item in self._store.messages.values()
        ):
            raise DomainValidationError("message id already exists")
        self._store.messages[message.id] = message

    async def get_message(
        self, conversation_id: UUID, external_id: str
    ) -> ConversationMessage | None:
        return next(
            (
                item
                for item in self._store.messages.values()
                if item.conversation_id == conversation_id and item.external_id == external_id
            ),
            None,
        )

    async def add_source(self, source: Source) -> None:
        if source.project_id not in self._store.projects:
            raise DomainValidationError("source project does not exist")
        self._store.sources[source.id] = source

    async def get_source(
        self, project_id: UUID, kind: SourceKind, title: str
    ) -> Source | None:
        return next(
            (
                item
                for item in self._store.sources.values()
                if item.project_id == project_id and item.kind is kind and item.title == title
            ),
            None,
        )

    async def add_version(self, version: SourceVersion) -> None:
        if version.source_id not in self._store.sources:
            raise DomainValidationError("source version parent does not exist")
        duplicate = any(
            item.source_id == version.source_id and item.content_hash == version.content_hash
            for item in self._store.versions.values()
        )
        if duplicate:
            raise DomainValidationError("source content hash already exists")
        self._store.versions[version.id] = version

    async def get_version(self, version_id: UUID) -> SourceVersion | None:
        return self._store.versions.get(version_id)

    async def get_pdf_version_by_hash(
        self, project_id: UUID, content_hash: str
    ) -> SourceVersion | None:
        source_ids = {
            source.id
            for source in self._store.sources.values()
            if source.project_id == project_id and source.kind is SourceKind.PDF
        }
        return next(
            (
                item
                for item in self._store.versions.values()
                if item.source_id in source_ids and item.content_hash == content_hash
            ),
            None,
        )

    async def next_version_number(self, source_id: UUID) -> int:
        versions = [
            item.version for item in self._store.versions.values() if item.source_id == source_id
        ]
        return max(versions, default=0) + 1

    async def add_block(self, block: ContentBlock) -> None:
        if block.source_version_id not in self._store.versions:
            raise DomainValidationError("content block source version does not exist")
        self._store.blocks[block.id] = block

    async def list_blocks(self, source_version_id: UUID) -> list[ContentBlock]:
        return sorted(
            (
                item
                for item in self._store.blocks.values()
                if item.source_version_id == source_version_id
            ),
            key=lambda item: item.ordinal,
        )


class InMemoryKnowledgeRepository:
    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    async def add_node(self, node: KnowledgeNode) -> None:
        if node.project_id not in self._store.projects:
            raise DomainValidationError("knowledge node project does not exist")
        self._store.nodes[node.id] = node

    async def get_node(self, node_id: UUID) -> KnowledgeNode | None:
        return self._store.nodes.get(node_id)

    async def save_node(self, node: KnowledgeNode) -> None:
        if node.id not in self._store.nodes:
            raise DomainValidationError("knowledge node does not exist")
        self._store.nodes[node.id] = node

    async def add_citation(self, citation: Citation) -> None:
        if citation.content_block_id not in self._store.blocks:
            raise DomainValidationError("citation content block does not exist")
        self._store.citations[citation.id] = citation

    async def add_claim(self, claim: Claim) -> None:
        if (
            claim.project_id not in self._store.projects
            or claim.subject_id not in self._store.nodes
        ):
            raise DomainValidationError("claim project or subject does not exist")
        if any(item.id not in self._store.citations for item in claim.citations):
            raise DomainValidationError("claim citation does not exist")
        self._store.claims[claim.id] = claim

    async def get_claim(self, claim_id: UUID) -> Claim | None:
        return self._store.claims.get(claim_id)

    async def save_claim(self, claim: Claim) -> None:
        if claim.id not in self._store.claims:
            raise DomainValidationError("claim does not exist")
        self._store.claims[claim.id] = claim

    async def add_relation(self, relation: Relation) -> None:
        if relation.relation_type not in self._store.relation_types:
            raise DomainValidationError("relation type does not exist")
        if (
            relation.source_id not in self._store.nodes
            or relation.target_id not in self._store.nodes
        ):
            raise DomainValidationError("relation endpoint does not exist")
        if any(item not in self._store.citations for item in relation.citation_ids):
            raise DomainValidationError("relation citation does not exist")
        self._store.relations[relation.id] = relation

    async def get_relation(self, relation_id: UUID) -> Relation | None:
        return self._store.relations.get(relation_id)

    async def save_relation(self, relation: Relation) -> None:
        if relation.id not in self._store.relations:
            raise DomainValidationError("relation does not exist")
        self._store.relations[relation.id] = relation

    async def add_relation_type(self, relation_type: RelationType) -> None:
        if relation_type.key in self._store.relation_types:
            raise DomainValidationError("relation type key already exists")
        self._store.relation_types[relation_type.key] = relation_type

    async def get_relation_type(self, key: str) -> RelationType | None:
        return self._store.relation_types.get(key)


class InMemoryGovernanceRepository:
    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    async def add_run(self, run: GovernanceRun) -> None:
        if run.project_id not in self._store.projects:
            raise DomainValidationError("governance project does not exist")
        self._store.governance_runs[run.id] = run

    async def add_issue(self, issue: GovernanceIssue) -> None:
        if issue.run_id not in self._store.governance_runs:
            raise DomainValidationError("governance run does not exist")
        self._store.governance_issues[issue.id] = issue

    async def add_duplicate_group(self, group: DuplicateGroup) -> None:
        if group.project_id not in self._store.projects:
            raise DomainValidationError("duplicate group project does not exist")
        self._store.duplicate_groups[group.id] = group

    async def add_conflict(self, conflict: ConflictRecord) -> None:
        if conflict.project_id not in self._store.projects:
            raise DomainValidationError("conflict project does not exist")
        self._store.conflicts[conflict.id] = conflict

    async def add_review_task(self, task: ReviewTask) -> None:
        if task.run_id not in self._store.governance_runs:
            raise DomainValidationError("review task governance run does not exist")
        self._store.review_tasks[task.id] = task

    async def get_review_task(self, task_id: UUID) -> ReviewTask | None:
        return self._store.review_tasks.get(task_id)

    async def save_review_task(self, task: ReviewTask) -> None:
        if task.id not in self._store.review_tasks:
            raise DomainValidationError("review task does not exist")
        self._store.review_tasks[task.id] = task

    async def list_review_tasks(self, *, limit: int = 100) -> list[ReviewTask]:
        tasks = sorted(
            self._store.review_tasks.values(),
            key=lambda item: item.created_at,
            reverse=True,
        )
        return tasks[:limit]


class InMemoryJobRepository:
    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    async def add(self, job: Job) -> None:
        if any(item.idempotency_key == job.idempotency_key for item in self._store.jobs.values()):
            raise DomainValidationError("job idempotency key already exists")
        self._store.jobs[job.id] = job

    async def save(self, job: Job) -> None:
        if job.id not in self._store.jobs:
            raise DomainValidationError("job does not exist")
        self._store.jobs[job.id] = job

    async def get(self, job_id: UUID) -> Job | None:
        return self._store.jobs.get(job_id)

    async def get_by_idempotency_key(self, key: str) -> Job | None:
        return next(
            (item for item in self._store.jobs.values() if item.idempotency_key == key),
            None,
        )

    async def list(self, *, limit: int = 100) -> list[Job]:
        jobs = sorted(self._store.jobs.values(), key=lambda item: item.created_at, reverse=True)
        return jobs[:limit]


class InMemoryUnitOfWork:
    def __init__(self, store: InMemoryStore) -> None:
        self._root_store = store
        self._working_store = store.clone()
        self.sources = InMemorySourceRepository(self._working_store)
        self.knowledge = InMemoryKnowledgeRepository(self._working_store)
        self.governance = InMemoryGovernanceRepository(self._working_store)
        self.jobs = InMemoryJobRepository(self._working_store)
        self._committed = False

    async def __aenter__(self) -> "InMemoryUnitOfWork":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if exc_type is not None or not self._committed:
            await self.rollback()

    async def commit(self) -> None:
        committed = self._working_store.clone()
        for field_name in committed.__dataclass_fields__:
            setattr(self._root_store, field_name, getattr(committed, field_name))
        self._committed = True

    async def rollback(self) -> None:
        self._working_store = self._root_store.clone()


class InMemoryUnitOfWorkFactory:
    def __init__(self, store: InMemoryStore | None = None) -> None:
        self.store = store or InMemoryStore()

    def __call__(self) -> InMemoryUnitOfWork:
        return InMemoryUnitOfWork(self.store)


class InMemoryJobQueue:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[UUID] = asyncio.Queue()

    async def enqueue(self, job_id: UUID) -> None:
        await self._queue.put(job_id)

    async def dequeue(self, *, timeout_seconds: float | None = None) -> UUID | None:
        if timeout_seconds is None:
            return await self._queue.get()
        try:
            return await asyncio.wait_for(self._queue.get(), timeout_seconds)
        except TimeoutError:
            return None
