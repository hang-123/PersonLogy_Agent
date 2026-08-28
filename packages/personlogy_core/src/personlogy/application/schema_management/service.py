"""Schema proposal and compatibility checks independent of Gel."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from personlogy.domain.schema.models import (
    SchemaChange,
    SchemaChangeKind,
    SchemaProposal,
    SchemaProposalStatus,
)
from personlogy.ports.schema_management import SchemaRegistry
from personlogy.shared.errors import DomainValidationError


class SchemaChangeService:
    def __init__(self, registry: SchemaRegistry) -> None:
        self._registry = registry

    async def propose(
        self,
        *,
        namespace: str,
        target_definition: dict[str, object],
        author: str,
    ) -> SchemaProposal:
        current = await self._registry.get_current_snapshot(namespace)
        if current is None:
            raise DomainValidationError("schema namespace has no current snapshot")
        changes = diff_schema(current.definition, target_definition)
        proposal = SchemaProposal(
            namespace=namespace,
            base_version=current.version,
            target_version=current.version + 1,
            definition=target_definition,
            changes=changes,
            author=author,
        )
        await self._registry.save_proposal(proposal)
        return proposal

    async def validate(self, proposal_id: UUID) -> SchemaProposal:
        proposal = await self._registry.get_proposal(proposal_id)
        if proposal is None:
            raise DomainValidationError("schema proposal does not exist")
        errors = validate_schema_definition(proposal.definition)
        current = await self._registry.get_current_snapshot(proposal.namespace)
        if current is None or current.version != proposal.base_version:
            errors.append("proposal base version is stale")
        if not proposal.changes:
            errors.append("schema proposal does not change the definition")
        status = SchemaProposalStatus.VALIDATED if not errors else SchemaProposalStatus.REJECTED
        updated = replace(
            proposal,
            status=status,
            validated_at=datetime.now(UTC),
        )
        await self._registry.save_proposal(updated)
        if errors:
            raise DomainValidationError("; ".join(errors))
        return updated


def diff_schema(
    before: Mapping[str, object], after: Mapping[str, object]
) -> tuple[SchemaChange, ...]:
    before_entities = _entities(before)
    after_entities = _entities(after)
    changes: list[SchemaChange] = []
    for name in sorted(after_entities.keys() - before_entities.keys()):
        changes.append(
            SchemaChange(SchemaChangeKind.ADD_ENTITY, f"entities.{name}", after_entities[name])
        )
    for name in sorted(before_entities.keys() - after_entities.keys()):
        changes.append(
            SchemaChange(
                SchemaChangeKind.REMOVE_ENTITY, f"entities.{name}", before_entities[name]
            )
        )
    for entity in sorted(before_entities.keys() & after_entities.keys()):
        before_fields = _fields(before_entities[entity])
        after_fields = _fields(after_entities[entity])
        for field_name in sorted(after_fields.keys() - before_fields.keys()):
            changes.append(
                SchemaChange(
                    SchemaChangeKind.ADD_FIELD,
                    f"entities.{entity}.fields.{field_name}",
                    after=after_fields[field_name],
                )
            )
        for field_name in sorted(before_fields.keys() - after_fields.keys()):
            changes.append(
                SchemaChange(
                    SchemaChangeKind.REMOVE_FIELD,
                    f"entities.{entity}.fields.{field_name}",
                    before=before_fields[field_name],
                )
            )
        for field_name in sorted(before_fields.keys() & after_fields.keys()):
            if before_fields[field_name] != after_fields[field_name]:
                changes.append(
                    SchemaChange(
                        SchemaChangeKind.CHANGE_FIELD,
                        f"entities.{entity}.fields.{field_name}",
                        before=before_fields[field_name],
                        after=after_fields[field_name],
                    )
                )
    return tuple(changes)


def validate_schema_definition(definition: Mapping[str, object]) -> list[str]:
    errors: list[str] = []
    entities = definition.get("entities")
    if not isinstance(entities, dict) or not entities:
        return ["schema definition must contain a non-empty entities object"]
    for entity_name, entity in entities.items():
        if not isinstance(entity_name, str) or not entity_name.strip():
            errors.append("entity names must be non-empty strings")
        if not isinstance(entity, dict):
            errors.append(f"entity {entity_name} must be an object")
            continue
        fields = entity.get("fields")
        if not isinstance(fields, dict):
            errors.append(f"entity {entity_name} must contain a fields object")
            continue
        for field_name, field in fields.items():
            if not isinstance(field_name, str) or not field_name.strip():
                errors.append(f"entity {entity_name} has an invalid field name")
            if not isinstance(field, dict) or not isinstance(field.get("type"), str):
                errors.append(f"field {entity_name}.{field_name} must declare a type")
    return errors


def _entities(definition: Mapping[str, object]) -> dict[str, object]:
    value = definition.get("entities", {})
    return cast(dict[str, object], value) if isinstance(value, dict) else {}


def _fields(entity: object) -> dict[str, object]:
    if not isinstance(entity, dict):
        return {}
    value = entity.get("fields", {})
    return cast(dict[str, object], value) if isinstance(value, dict) else {}


__all__ = ["SchemaChangeService", "diff_schema", "validate_schema_definition"]
