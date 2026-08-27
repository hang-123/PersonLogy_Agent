"""Application service for candidate knowledge compilation."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from uuid import UUID

from personlogy.application.governance import GovernanceEvaluator
from personlogy.application.orchestration import JobService
from personlogy.domain.governance.models import GovernanceRunStatus
from personlogy.domain.job import Job
from personlogy.domain.knowledge.models import VerificationStatus
from personlogy.domain.source.models import ContentBlock
from personlogy.ports.compilation import CompilationBundle, KnowledgeCompiler
from personlogy.ports.ingestion import ObjectStorage
from personlogy.ports.unit_of_work import UnitOfWorkFactory
from personlogy.shared.errors import DomainValidationError


@dataclass(frozen=True, slots=True)
class CompilationResult:
    job_id: UUID
    source_version_id: UUID
    node_count: int
    citation_count: int
    claim_count: int
    relation_count: int
    okf_object_key: str
    prompt_version: str
    model_name: str
    governance_status: str
    governance_run_id: UUID
    review_task_count: int
    issue_count: int


class CompilationService:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        job_service: JobService,
        compiler: KnowledgeCompiler,
        okf_storage: ObjectStorage,
        governance_evaluator: GovernanceEvaluator | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._job_service = job_service
        self._compiler = compiler
        self._okf_storage = okf_storage
        self._governance_evaluator = governance_evaluator or GovernanceEvaluator()

    async def submit_for_version(
        self, *, project_id: UUID, source_version_id: UUID
    ) -> Job:
        return await self._job_service.submit(
            kind="knowledge.compile",
            idempotency_key=f"knowledge-compile:{source_version_id}",
            payload={
                "project_id": str(project_id),
                "source_version_id": str(source_version_id),
                "compiler": self._compiler.model_name,
                "prompt_version": self._compiler.prompt_version,
            },
        )

    async def process_compile_job(self, job: Job) -> CompilationResult:
        if job.kind != "knowledge.compile":
            raise DomainValidationError(f"unsupported compilation job kind: {job.kind}")
        project_id = _payload_uuid(job, "project_id")
        source_version_id = _payload_uuid(job, "source_version_id")

        async with self._uow_factory() as uow:
            blocks = tuple(await uow.sources.list_blocks(source_version_id))
        if not blocks:
            raise DomainValidationError("source version has no content blocks")

        bundle = self._compiler.compile(project_id=project_id, blocks=blocks)
        self._validate_bundle(bundle, project_id, blocks)
        evaluation = self._governance_evaluator.evaluate(
            project_id=project_id,
            task_id=job.id,
            bundle=bundle,
        )
        bundle = _apply_governance(bundle, evaluation.run.status)
        metadata = {
            "task_id": str(job.id),
            "prompt_version": bundle.prompt_version,
            "model_name": bundle.model_name,
            "generated_at": bundle.generated_at.isoformat(),
        }
        bundle = _with_metadata(bundle, metadata)
        okf_key = f"projects/{project_id}/compilations/{job.id}.okf.json"
        await self._okf_storage.put(
            okf_key,
            json.dumps(bundle.okf, ensure_ascii=False, indent=2).encode("utf-8"),
        )

        async with self._uow_factory() as uow:
            for citation in bundle.citations:
                await uow.knowledge.add_citation(citation)
            for node in bundle.nodes:
                await uow.knowledge.add_node(node)
            for claim in bundle.claims:
                await uow.knowledge.add_claim(claim)
            for relation_type in bundle.relation_types:
                if await uow.knowledge.get_relation_type(relation_type.key) is None:
                    await uow.knowledge.add_relation_type(relation_type)
            for relation in bundle.relations:
                await uow.knowledge.add_relation(relation)
            await uow.governance.add_run(evaluation.run)
            for issue in evaluation.issues:
                await uow.governance.add_issue(issue)
            for group in evaluation.duplicate_groups:
                await uow.governance.add_duplicate_group(group)
            for conflict in evaluation.conflicts:
                await uow.governance.add_conflict(conflict)
            for review_task in evaluation.review_tasks:
                await uow.governance.add_review_task(review_task)
            await uow.commit()

        return CompilationResult(
            job_id=job.id,
            source_version_id=source_version_id,
            node_count=len(bundle.nodes),
            citation_count=len(bundle.citations),
            claim_count=len(bundle.claims),
            relation_count=len(bundle.relations),
            okf_object_key=okf_key,
            prompt_version=bundle.prompt_version,
            model_name=bundle.model_name,
            governance_status=evaluation.run.status.value,
            governance_run_id=evaluation.run.id,
            review_task_count=len(evaluation.review_tasks),
            issue_count=len(evaluation.issues),
        )

    @staticmethod
    def _validate_bundle(
        bundle: CompilationBundle, project_id: UUID, blocks: tuple[ContentBlock, ...]
    ) -> None:
        block_ids = {block.id for block in blocks}
        node_ids = {node.id for node in bundle.nodes}
        citation_ids = {citation.id for citation in bundle.citations}
        if not bundle.nodes and not bundle.claims and not bundle.relations:
            raise DomainValidationError("compiler returned no candidate knowledge")
        if any(citation.content_block_id not in block_ids for citation in bundle.citations):
            raise DomainValidationError("compiler returned citation for unknown content block")
        if any(node.project_id != project_id for node in bundle.nodes):
            raise DomainValidationError("compiler returned node for another project")
        if any(
            claim.project_id != project_id
            or claim.subject_id not in node_ids
            or any(citation.id not in citation_ids for citation in claim.citations)
            for claim in bundle.claims
        ):
            raise DomainValidationError("compiler returned claim with invalid provenance")
        relation_type_keys = {item.key for item in bundle.relation_types}
        if any(
            relation.project_id != project_id
            or relation.source_id not in node_ids
            or relation.target_id not in node_ids
            or relation.relation_type not in relation_type_keys
            or any(item not in citation_ids for item in relation.citation_ids)
            for relation in bundle.relations
        ):
            raise DomainValidationError("compiler returned relation with invalid provenance")


def _with_metadata(
    bundle: CompilationBundle, metadata: Mapping[str, object]
) -> CompilationBundle:
    nodes = tuple(
        replace(node, properties={**node.properties, "compilation": metadata})
        for node in bundle.nodes
    )
    citations = tuple(
        replace(citation, metadata={**citation.metadata, "compilation": metadata})
        for citation in bundle.citations
    )
    claims = tuple(
        replace(claim, metadata={**claim.metadata, "compilation": metadata})
        for claim in bundle.claims
    )
    relations = tuple(
        replace(
            relation,
            properties={**relation.properties, "compilation": metadata},
            metadata={**relation.metadata, "compilation": metadata},
        )
        for relation in bundle.relations
    )
    okf = {
        **bundle.okf,
        "provenance": {**_as_dict(bundle.okf.get("provenance")), **metadata},
    }
    return replace(
        bundle,
        nodes=nodes,
        citations=citations,
        claims=claims,
        relations=relations,
        okf=okf,
    )


def _apply_governance(
    bundle: CompilationBundle, status: GovernanceRunStatus
) -> CompilationBundle:
    candidate_status = (
        VerificationStatus.REJECTED
        if status is GovernanceRunStatus.REJECTED
        else VerificationStatus.MACHINE_CHECKED
    )
    nodes = tuple(replace(node, status=candidate_status) for node in bundle.nodes)
    claims = tuple(replace(claim, status=candidate_status) for claim in bundle.claims)
    relations = tuple(replace(relation, status=candidate_status) for relation in bundle.relations)
    okf = {
        **bundle.okf,
        "governance": {
            "status": status.value,
            "rule_version": "p6-rules-v1",
            "review_required": status is GovernanceRunStatus.NEEDS_REVIEW,
        },
    }
    return replace(bundle, nodes=nodes, claims=claims, relations=relations, okf=okf)


def _as_dict(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _payload_uuid(job: Job, key: str) -> UUID:
    value = job.payload.get(key)
    if not isinstance(value, str):
        raise DomainValidationError(f"compilation job payload field is missing: {key}")
    try:
        return UUID(value)
    except ValueError as error:
        raise DomainValidationError(
            f"compilation job payload field is invalid: {key}"
        ) from error
