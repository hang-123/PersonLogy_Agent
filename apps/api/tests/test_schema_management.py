import asyncio
from pathlib import Path

import pytest
from personlogy.adapters.sqlite import SQLiteStore
from personlogy.adapters.sqlite_features import SQLiteFeatureStore, SQLiteSchemaRegistry
from personlogy.application.schema_management import SchemaChangeService, diff_schema
from personlogy.domain.schema.models import (
    SchemaChangeKind,
    SchemaProposalStatus,
    SchemaSnapshot,
)


def test_schema_proposal_diff_and_validation_are_persisted(tmp_path: Path) -> None:
    asyncio.run(_test_schema_proposal_diff_and_validation_are_persisted(tmp_path))


async def _test_schema_proposal_diff_and_validation_are_persisted(tmp_path: Path) -> None:
    database = tmp_path / "personlogy.sqlite3"
    SQLiteStore(database)
    registry = SQLiteSchemaRegistry(SQLiteFeatureStore(database))
    initial = SchemaSnapshot.create(
        namespace="knowledge",
        version=1,
        definition={
            "entities": {
                "Claim": {"fields": {"statement": {"type": "text", "required": True}}}
            }
        },
    )
    await registry.save_snapshot(initial)
    service = SchemaChangeService(registry)
    proposal = await service.propose(
        namespace="knowledge",
        target_definition={
            "entities": {
                "Claim": {
                    "fields": {
                        "statement": {"type": "text", "required": True},
                        "confidence": {"type": "float", "required": False},
                    }
                }
            }
        },
        author="test-user",
    )

    assert proposal.target_version == 2
    assert proposal.changes[0].kind is SchemaChangeKind.ADD_FIELD
    validated = await service.validate(proposal.id)
    assert validated.status is SchemaProposalStatus.VALIDATED
    reloaded = await registry.get_proposal(proposal.id)
    assert reloaded is not None
    assert reloaded.status is SchemaProposalStatus.VALIDATED


def test_schema_diff_detects_removed_and_changed_fields() -> None:
    changes = diff_schema(
        {
            "entities": {
                "Claim": {
                    "fields": {"statement": {"type": "text"}, "old": {"type": "text"}}
                }
            }
        },
        {"entities": {"Claim": {"fields": {"statement": {"type": "string"}}}}},
    )
    assert {change.kind for change in changes} == {
        SchemaChangeKind.REMOVE_FIELD,
        SchemaChangeKind.CHANGE_FIELD,
    }


def test_schema_proposal_requires_approval_and_supports_execute_rollback(tmp_path: Path) -> None:
    asyncio.run(_test_schema_proposal_requires_approval_and_supports_execute_rollback(tmp_path))


async def _test_schema_proposal_requires_approval_and_supports_execute_rollback(
    tmp_path: Path,
) -> None:
    database = tmp_path / "personlogy.sqlite3"
    SQLiteStore(database)
    registry = SQLiteSchemaRegistry(SQLiteFeatureStore(database))
    initial_definition = {
        "entities": {"Claim": {"fields": {"statement": {"type": "text"}}}}
    }
    await registry.save_snapshot(
        SchemaSnapshot.create(namespace="knowledge", version=1, definition=initial_definition)
    )
    service = SchemaChangeService(registry)
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
        author="author",
    )

    with pytest.raises(ValueError, match="approved"):
        await service.execute(proposal.id)
    validated = await service.validate(proposal.id)
    approved = await service.approve(validated.id, approver="reviewer")
    assert approved.status is SchemaProposalStatus.APPROVED
    assert approved.approved_by == "reviewer"

    applied = await service.execute(approved.id)
    assert applied.status is SchemaProposalStatus.APPLIED
    assert applied.applied_at is not None
    current = await registry.get_current_snapshot("knowledge")
    assert current is not None and current.version == 2
    assert current.definition != initial_definition

    rolled_back = await service.rollback(applied.id)
    assert rolled_back.status is SchemaProposalStatus.ROLLED_BACK
    assert rolled_back.rolled_back_at is not None
    restored = await registry.get_current_snapshot("knowledge")
    assert restored is not None and restored.version == 3
    assert restored.definition == initial_definition
    assert await registry.get_snapshot("knowledge", 2) is not None


def test_schema_execution_rejects_stale_proposal(tmp_path: Path) -> None:
    asyncio.run(_test_schema_execution_rejects_stale_proposal(tmp_path))


async def _test_schema_execution_rejects_stale_proposal(tmp_path: Path) -> None:
    database = tmp_path / "personlogy.sqlite3"
    SQLiteStore(database)
    registry = SQLiteSchemaRegistry(SQLiteFeatureStore(database))
    await registry.save_snapshot(
        SchemaSnapshot.create(
            namespace="knowledge",
            version=1,
            definition={"entities": {"Claim": {"fields": {"a": {"type": "text"}}}}},
        )
    )
    service = SchemaChangeService(registry)
    first = await service.propose(
        namespace="knowledge",
        target_definition={"entities": {"Claim": {"fields": {"a": {"type": "int"}}}}},
        author="author-1",
    )
    second = await service.propose(
        namespace="knowledge",
        target_definition={"entities": {"Claim": {"fields": {"a": {"type": "bool"}}}}},
        author="author-2",
    )
    await service.validate(first.id)
    await service.approve(first.id, approver="reviewer")
    await service.validate(second.id)
    await service.approve(second.id, approver="reviewer")
    await service.execute(first.id)
    with pytest.raises(ValueError, match=r"stale|failed"):
        await service.execute(second.id)
