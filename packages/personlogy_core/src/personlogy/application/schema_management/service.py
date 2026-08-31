"""Schema proposal and compatibility checks independent of Gel."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from personlogy.application.audit import append_audit_event
from personlogy.domain.audit import digest_for
from personlogy.domain.schema.models import (
    SchemaChange,
    SchemaChangeKind,
    SchemaProposal,
    SchemaProposalStatus,
    SchemaSnapshot,
)
from personlogy.ports.audit import AuditSink
from personlogy.ports.schema_management import MigrationExecutor, SchemaRegistry
from personlogy.shared.errors import DomainValidationError


class SchemaChangeService:
    def __init__(
        self,
        registry: SchemaRegistry,
        audit_sink: AuditSink | None = None,
        migration_executor: MigrationExecutor | None = None,
    ) -> None:
        self._registry = registry
        self._audit_sink = audit_sink
        self._migration_executor = migration_executor or RegistryMigrationExecutor()

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
        await append_audit_event(
            self._audit_sink,
            event_type="schema.proposal.created",
            status=proposal.status.value,
            entity_type="schema_proposal",
            entity_id=str(proposal.id),
            before={"version": current.version, "checksum": current.checksum},
            after={"version": proposal.target_version, "definition": target_definition},
            metadata={
                "namespace": namespace,
                "base_version": proposal.base_version,
                "target_version": proposal.target_version,
                "change_count": len(changes),
                "author_digest": digest_for(author),
            },
        )
        return proposal

    async def get(self, proposal_id: UUID) -> SchemaProposal | None:
        return await self._registry.get_proposal(proposal_id)

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
        await append_audit_event(
            self._audit_sink,
            event_type="schema.proposal.validated" if not errors else "schema.proposal.rejected",
            status=updated.status.value,
            entity_type="schema_proposal",
            entity_id=str(updated.id),
            before={"status": proposal.status.value},
            after={"status": updated.status.value, "validated": not bool(errors)},
            reason_code="schema_validation_failed" if errors else None,
            metadata={
                "namespace": updated.namespace,
                "proposal_id": str(updated.id),
                "base_version": updated.base_version,
                "target_version": updated.target_version,
                "errors_digest": digest_for(errors),
            },
        )
        if errors:
            raise DomainValidationError("; ".join(errors))
        return updated

    async def approve(
        self, proposal_id: UUID, *, approver: str
    ) -> SchemaProposal:
        proposal = await self._get_proposal(proposal_id)
        if proposal.status is not SchemaProposalStatus.VALIDATED:
            raise DomainValidationError("only a validated schema proposal can be approved")
        if not approver.strip():
            raise DomainValidationError("schema approver is required")
        approved = replace(
            proposal,
            status=SchemaProposalStatus.APPROVED,
            approved_by=approver,
            approved_at=datetime.now(UTC),
        )
        await self._registry.save_proposal(approved)
        await append_audit_event(
            self._audit_sink,
            event_type="schema.proposal.approved",
            status=approved.status.value,
            entity_type="schema_proposal",
            entity_id=str(approved.id),
            before={"status": proposal.status.value},
            after={"status": approved.status.value, "approved_at": approved.approved_at},
            metadata={
                "namespace": approved.namespace,
                "proposal_id": str(approved.id),
                "base_version": approved.base_version,
                "target_version": approved.target_version,
                "actor_id_digest": digest_for(approver),
            },
        )
        return approved

    async def execute(self, proposal_id: UUID) -> SchemaProposal:
        proposal = await self._get_proposal(proposal_id)
        if proposal.status is not SchemaProposalStatus.APPROVED:
            raise DomainValidationError("only an approved schema proposal can be executed")
        current = await self._registry.get_current_snapshot(proposal.namespace)
        if current is None or current.version != proposal.base_version:
            await self._record_execution_failure(
                proposal, "schema_version_conflict", current=current
            )
            raise DomainValidationError("schema proposal base version is stale")
        try:
            await self._migration_executor.apply(proposal=proposal, current=current)
            applied_snapshot = SchemaSnapshot.create(
                namespace=proposal.namespace,
                version=proposal.target_version,
                definition=proposal.definition,
            )
            await self._registry.save_snapshot_if_current(
                applied_snapshot, expected_version=current.version
            )
        except Exception as error:
            await self._record_execution_failure(
                proposal, "schema_execution_failed", current=current, error=error
            )
            raise DomainValidationError("schema proposal execution failed") from error

        applied = replace(
            proposal,
            status=SchemaProposalStatus.APPLIED,
            applied_at=datetime.now(UTC),
        )
        await self._registry.save_proposal(applied)
        await append_audit_event(
            self._audit_sink,
            event_type="schema.proposal.applied",
            status=applied.status.value,
            entity_type="schema_proposal",
            entity_id=str(applied.id),
            before={"status": proposal.status.value, "version": current.version},
            after={"status": applied.status.value, "version": applied.target_version},
            metadata={
                "namespace": applied.namespace,
                "proposal_id": str(applied.id),
                "base_version": applied.base_version,
                "target_version": applied.target_version,
                "change_count": len(applied.changes),
            },
        )
        return applied

    async def rollback(self, proposal_id: UUID) -> SchemaProposal:
        proposal = await self._get_proposal(proposal_id)
        if proposal.status is not SchemaProposalStatus.APPLIED:
            raise DomainValidationError("only an applied schema proposal can be rolled back")
        current = await self._registry.get_current_snapshot(proposal.namespace)
        target = await self._registry.get_snapshot(proposal.namespace, proposal.base_version)
        if current is None or target is None:
            raise DomainValidationError("schema rollback snapshots are unavailable")
        if current.version != proposal.target_version:
            raise DomainValidationError(
                "schema rollback is blocked because a newer version is already current"
            )
        try:
            await self._migration_executor.rollback(
                proposal=proposal, current=current, target=target
            )
            rollback_snapshot = SchemaSnapshot.create(
                namespace=proposal.namespace,
                version=current.version + 1,
                definition=target.definition,
            )
            await self._registry.save_snapshot_if_current(
                rollback_snapshot, expected_version=current.version
            )
        except Exception as error:
            await append_audit_event(
                self._audit_sink,
                event_type="schema.proposal.rollback_failed",
                status="failed",
                entity_type="schema_proposal",
                entity_id=str(proposal.id),
                before={"status": proposal.status.value, "version": current.version},
                reason_code="schema_rollback_failed",
                metadata={
                    "namespace": proposal.namespace,
                    "proposal_id": str(proposal.id),
                    "errors_digest": digest_for(str(error)),
                },
            )
            raise DomainValidationError("schema proposal rollback failed") from error

        rolled_back = replace(
            proposal,
            status=SchemaProposalStatus.ROLLED_BACK,
            rolled_back_at=datetime.now(UTC),
        )
        await self._registry.save_proposal(rolled_back)
        await append_audit_event(
            self._audit_sink,
            event_type="schema.proposal.rolled_back",
            status=rolled_back.status.value,
            entity_type="schema_proposal",
            entity_id=str(rolled_back.id),
            before={"status": proposal.status.value, "version": current.version},
            after={"status": rolled_back.status.value, "version": current.version + 1},
            metadata={
                "namespace": rolled_back.namespace,
                "proposal_id": str(rolled_back.id),
                "base_version": rolled_back.base_version,
                "target_version": current.version + 1,
            },
        )
        return rolled_back

    async def _get_proposal(self, proposal_id: UUID) -> SchemaProposal:
        proposal = await self._registry.get_proposal(proposal_id)
        if proposal is None:
            raise DomainValidationError("schema proposal does not exist")
        return proposal

    async def _record_execution_failure(
        self,
        proposal: SchemaProposal,
        reason_code: str,
        *,
        current: SchemaSnapshot | None,
        error: Exception | None = None,
    ) -> None:
        await append_audit_event(
            self._audit_sink,
            event_type="schema.proposal.execution_failed",
            status="failed",
            entity_type="schema_proposal",
            entity_id=str(proposal.id),
            before={
                "status": proposal.status.value,
                "version": current.version if current else None,
            },
            reason_code=reason_code,
            metadata={
                "namespace": proposal.namespace,
                "proposal_id": str(proposal.id),
                "errors_digest": digest_for(str(error or reason_code)),
            },
        )


class RegistryMigrationExecutor:
    """Safe local executor for logical registry snapshots.

    SQLite stores the versioned schema contract rather than altering its own
    physical tables. A Gel or database-specific executor can be injected for
    physical migration execution while retaining this service state machine.
    """

    async def apply(self, *, proposal: SchemaProposal, current: SchemaSnapshot) -> None:
        if (
            current.namespace != proposal.namespace
            or current.version != proposal.base_version
        ):
            raise DomainValidationError("migration current snapshot does not match proposal")

    async def rollback(
        self,
        *,
        proposal: SchemaProposal,
        current: SchemaSnapshot,
        target: SchemaSnapshot,
    ) -> None:
        if (
            current.namespace != proposal.namespace
            or target.version != proposal.base_version
        ):
            raise DomainValidationError("migration rollback snapshots do not match proposal")


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
