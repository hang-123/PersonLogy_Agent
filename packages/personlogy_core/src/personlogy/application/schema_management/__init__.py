"""Schema proposal, validation, approval, and migration workflows."""

from personlogy.application.schema_management.service import (
    RegistryMigrationExecutor,
    SchemaChangeService,
    diff_schema,
    validate_schema_definition,
)

__all__ = [
    "RegistryMigrationExecutor",
    "SchemaChangeService",
    "diff_schema",
    "validate_schema_definition",
]
