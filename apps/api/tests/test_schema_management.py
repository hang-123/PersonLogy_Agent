import asyncio
from pathlib import Path

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
