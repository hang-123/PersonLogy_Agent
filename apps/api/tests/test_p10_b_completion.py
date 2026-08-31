import asyncio
from collections.abc import Mapping
from pathlib import Path
from typing import cast
from uuid import uuid4

import pytest
from personlogy.adapters.sqlite import SQLiteStore, SQLiteUnitOfWorkFactory
from personlogy.adapters.sqlite_audit import SQLiteRecordStore
from personlogy.adapters.sqlite_features import (
    SQLiteFeatureStore,
    SQLiteRetrievalIndexer,
    SQLiteRetrievalReader,
    SQLiteSchemaRegistry,
)
from personlogy.adapters.sqlite_lineage import SQLiteLineageStore
from personlogy.application.governance import GovernanceService
from personlogy.application.lineage import LineageService
from personlogy.application.retrieval import RetrievalService
from personlogy.application.schema_management import SchemaChangeService
from personlogy.application.tool_gateway import (
    AuditedToolExecutor,
    AuditPolicyEngine,
    CallableAuditorProvider,
    ToolDeniedError,
)
from personlogy.domain.audit import AuditEvent, digest_for
from personlogy.domain.governance.models import (
    CandidateKind,
    GovernanceRun,
    GovernanceRunStatus,
    ReviewTask,
    ReviewTaskStatus,
)
from personlogy.domain.knowledge.models import Citation, Claim, KnowledgeNode, VerificationStatus
from personlogy.domain.schema.models import SchemaProposalStatus, SchemaSnapshot
from personlogy.domain.source.models import ContentBlock, Project, Source, SourceKind, SourceVersion
from personlogy.ports.tools import AuditDecision, ToolIntent
from personlogy.shared.errors import DomainValidationError


def test_audit_event_has_state_digests_and_rejects_raw_metadata(tmp_path: Path) -> None:
    asyncio.run(_test_audit_event_has_state_digests_and_rejects_raw_metadata(tmp_path))


async def _test_audit_event_has_state_digests_and_rejects_raw_metadata(tmp_path: Path) -> None:
    with pytest.raises(DomainValidationError, match="metadata field is not allowed"):
        AuditEvent(
            event_type="tool.requested",
            status="requested",
            trace_id="trace-sensitive",
            actor_type="system",
            entity_type="tool_invocation",
            metadata={"prompt": "SENSITIVE_RAW_SAMPLE"},
        )

    store = SQLiteRecordStore(tmp_path / "personlogy.sqlite3")
    event = AuditEvent(
        event_type="review_task.decided",
        status="approved",
        trace_id="trace-digest",
        actor_type="user",
        entity_type="review_task",
        before_digest=digest_for({"status": "pending"}),
        after_digest=digest_for({"status": "approved"}),
    )
    stored = await store.append(event)
    reloaded = await store.get(stored.event_id)
    assert reloaded is not None
    assert reloaded.before_digest == event.before_digest
    assert reloaded.after_digest == event.after_digest


def test_governance_service_records_decision_audit(tmp_path: Path) -> None:
    asyncio.run(_test_governance_service_records_decision_audit(tmp_path))


async def _test_governance_service_records_decision_audit(tmp_path: Path) -> None:
    database = tmp_path / "personlogy.sqlite3"
    store = SQLiteStore(database)
    audit = SQLiteRecordStore(database)
    factory = SQLiteUnitOfWorkFactory(store)
    project = Project("治理审计", "governance-audit")
    node = KnowledgeNode(project.id, "topic", "审计节点")
    run = GovernanceRun(
        project.id,
        uuid4(),
        "rules-1",
        GovernanceRunStatus.NEEDS_REVIEW,
        (node.id,),
    )
    task = ReviewTask(run.id, node.id, CandidateKind.NODE)
    async with factory() as uow:
        await uow.sources.add_project(project)
        await uow.knowledge.add_node(node)
        await uow.governance.add_run(run)
        await uow.governance.add_review_task(task)
        await uow.commit()

    service = GovernanceService(factory, audit_sink=audit)
    updated = await service.decide_review_task(
        task.id,
        decision=ReviewTaskStatus.APPROVED,
        reviewer_id="reviewer-1",
        reason="candidate is supported",
    )
    events = await audit.list(entity_id=str(task.id))
    assert updated.status is ReviewTaskStatus.APPROVED
    assert [event.event_type for event in events] == ["review_task.decided"]
    assert events[0].before_digest is not None
    assert events[0].after_digest is not None
    assert events[0].metadata["reason_digest"] == digest_for("candidate is supported")
    assert "candidate is supported" not in events[0].canonical_json()


def test_schema_service_records_proposal_lifecycle(tmp_path: Path) -> None:
    asyncio.run(_test_schema_service_records_proposal_lifecycle(tmp_path))


async def _test_schema_service_records_proposal_lifecycle(tmp_path: Path) -> None:
    database = tmp_path / "personlogy.sqlite3"
    SQLiteStore(database)
    audit = SQLiteRecordStore(database)
    registry = SQLiteSchemaRegistry(SQLiteFeatureStore(database))
    await registry.save_snapshot(
        SchemaSnapshot.create(
            namespace="knowledge",
            version=1,
            definition={"entities": {"Claim": {"fields": {"statement": {"type": "text"}}}}},
        )
    )
    service = SchemaChangeService(registry, audit_sink=audit)
    proposal = await service.propose(
        namespace="knowledge",
        target_definition={
            "entities": {
                "Claim": {
                    "fields": {
                        "statement": {"type": "text"},
                        "confidence": {"type": "float"},
                    }
                }
            }
        },
        author="schema-author",
    )
    validated = await service.validate(proposal.id)
    events = await audit.list(entity_id=str(proposal.id))
    assert validated.status is SchemaProposalStatus.VALIDATED
    assert [event.event_type for event in events] == [
        "schema.proposal.created",
        "schema.proposal.validated",
    ]
    assert events[0].before_digest is not None
    assert events[0].after_digest is not None


def test_retrieval_and_index_build_record_audit(tmp_path: Path) -> None:
    asyncio.run(_test_retrieval_and_index_build_record_audit(tmp_path))


async def _test_retrieval_and_index_build_record_audit(tmp_path: Path) -> None:
    database = tmp_path / "personlogy.sqlite3"
    store = SQLiteStore(database)
    features = SQLiteFeatureStore(database)
    audit = SQLiteRecordStore(database)
    lineage = SQLiteLineageStore(database)
    factory = SQLiteUnitOfWorkFactory(store)
    project = Project("检索审计", "retrieval-audit")
    source = Source(project.id, SourceKind.PDF, "审计来源")
    version = SourceVersion(source.id, 1, "source-hash", "sources/source.pdf")
    block = ContentBlock(version.id, 0, "可追踪的检索证据。", "block-hash", {"page": 1})
    node = KnowledgeNode(
        project.id,
        "topic",
        "审计主题",
        status=VerificationStatus.HUMAN_VERIFIED,
    )
    citation = Citation(block.id, "可追踪的检索证据。", {"page": 1})
    claim = Claim(
        project.id,
        node.id,
        "可追踪的检索证据",
        (citation,),
        status=VerificationStatus.HUMAN_VERIFIED,
    )
    async with factory() as uow:
        await uow.sources.add_project(project)
        await uow.sources.add_source(source)
        await uow.sources.add_version(version)
        await uow.sources.add_block(block)
        await uow.knowledge.add_node(node)
        await uow.knowledge.add_citation(citation)
        await uow.knowledge.add_claim(claim)
        await uow.commit()

    indexer = SQLiteRetrievalIndexer(
        features,
        audit_sink=audit,
        lineage_store=lineage,
    )
    assert await indexer.rebuild_project(project.id) == 1
    retrieval = RetrievalService(
        SQLiteRetrievalReader(features),
        audit_sink=audit,
        lineage_store=lineage,
    )
    hits = await retrieval.search(project_id=project.id, query="可追踪的检索证据")
    assert len(hits) == 1
    assert [event.event_type for event in await audit.list(event_type="index_build.started")] == [
        "index_build.started"
    ]
    assert [event.event_type for event in await audit.list(event_type="index_build.succeeded")] == [
        "index_build.succeeded"
    ]
    retrieval_events = await audit.list(event_type="retrieval.succeeded")
    assert len(retrieval_events) == 1
    assert retrieval_events[0].metadata["result_count"] == 1
    assert retrieval_events[0].metadata["query_digest"] == digest_for("可追踪的检索证据")
    trace = await LineageService(lineage).trace_retrieval(
        project_id=project.id,
        request_id=cast(str, retrieval_events[0].metadata["retrieval_request_id"]),
    )
    assert any(link.to_type == "claim" and link.to_id == str(claim.id) for link in trace.links)
    assert any(
        link.to_type == "source_version" and link.to_id == str(version.id)
        for link in trace.links
    )


def test_tool_gateway_is_audited_and_fail_closed(tmp_path: Path) -> None:
    asyncio.run(_test_tool_gateway_is_audited_and_fail_closed(tmp_path))


async def _test_tool_gateway_is_audited_and_fail_closed(tmp_path: Path) -> None:
    audit = SQLiteRecordStore(tmp_path / "personlogy.sqlite3")
    observed: list[dict[str, object]] = []

    async def review(*, intent: ToolIntent, context: Mapping[str, object]) -> AuditDecision:
        observed.append(dict(intent.arguments))
        assert "value" not in intent.arguments
        return AuditDecision("allow", required_checks=("scope",))

    async def tool(arguments: object) -> object:
        assert cast(dict[str, object], arguments)["value"] == "secret-in-memory-only"
        return {"ok": True}

    executor = AuditedToolExecutor(
        audit,
        CallableAuditorProvider(review),
        AuditPolicyEngine(policy_version="policy-test"),
    )
    intent = ToolIntent(
        "demo.read",
        {"value": "secret-in-memory-only"},
        invocation_id="tool-allow-1",
    )
    assert await executor.execute(intent, tool) == {"ok": True}
    assert observed == [{"args_digest": digest_for({"value": "secret-in-memory-only"})}]
    events = await audit.list(entity_id=intent.invocation_id)
    assert [event.event_type for event in events] == [
        "tool.requested",
        "auditor.review.started",
        "auditor.review.succeeded",
        "tool.started",
        "tool.succeeded",
    ]
    assert all("secret-in-memory-only" not in event.canonical_json() for event in events)

    called = False

    async def denied_tool(arguments: object) -> object:
        nonlocal called
        called = True
        return arguments

    async def deny(*, intent: ToolIntent, context: Mapping[str, object]) -> AuditDecision:
        return AuditDecision("deny", reasons=("not approved",))

    denied_intent = ToolIntent("demo.write", {}, risk_class="write", invocation_id="tool-deny-1")
    denied_executor = AuditedToolExecutor(
        audit,
        CallableAuditorProvider(deny),
        AuditPolicyEngine(policy_version="policy-test"),
    )
    with pytest.raises(ToolDeniedError, match="auditor_deny"):
        await denied_executor.execute(denied_intent, denied_tool)
    assert called is False
    denied_events = await audit.list(entity_id=denied_intent.invocation_id)
    assert denied_events[-1].event_type == "tool.denied"

    async def broken_review(*, intent: ToolIntent, context: Mapping[str, object]) -> AuditDecision:
        raise TimeoutError("auditor timeout")

    failed_intent = ToolIntent("demo.read", {}, invocation_id="tool-fail-closed-1")
    failed_executor = AuditedToolExecutor(
        audit,
        CallableAuditorProvider(broken_review),
        AuditPolicyEngine(policy_version="policy-test"),
    )
    with pytest.raises(ToolDeniedError, match="audit review failed"):
        await failed_executor.execute(failed_intent, denied_tool)
    failed_events = await audit.list(entity_id=failed_intent.invocation_id)
    assert [event.event_type for event in failed_events] == [
        "tool.requested",
        "auditor.review.started",
        "auditor.review.failed",
        "tool.denied",
    ]
    assert called is False
