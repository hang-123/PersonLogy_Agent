"""Ports and value objects for provider-independent knowledge compilation."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from personlogy.domain.knowledge.models import Citation, Claim, KnowledgeNode
from personlogy.domain.relation.models import Relation, RelationType
from personlogy.domain.source.models import ContentBlock


@dataclass(frozen=True, slots=True)
class CompilationBundle:
    """Validated candidate objects and their portable OKF representation."""

    nodes: tuple[KnowledgeNode, ...]
    citations: tuple[Citation, ...]
    claims: tuple[Claim, ...]
    relations: tuple[Relation, ...]
    relation_types: tuple[RelationType, ...]
    okf: dict[str, object]
    prompt_version: str
    model_name: str
    generated_at: datetime

    @classmethod
    def metadata(
        cls, *, prompt_version: str, model_name: str, task_id: UUID
    ) -> dict[str, object]:
        return {
            "prompt_version": prompt_version,
            "model_name": model_name,
            "task_id": str(task_id),
            "generated_at": datetime.now(UTC).isoformat(),
        }


class KnowledgeCompiler(Protocol):
    """Compile content blocks without coupling the application to an LLM vendor."""

    prompt_version: str
    model_name: str

    def compile(
        self, *, project_id: UUID, blocks: tuple[ContentBlock, ...]
    ) -> CompilationBundle: ...
