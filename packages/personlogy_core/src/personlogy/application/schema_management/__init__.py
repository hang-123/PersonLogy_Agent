"""Schema proposal, validation, approval, and migration workflows."""

from personlogy.application.schema_management.service import (
    SchemaChangeService,
    diff_schema,
    validate_schema_definition,
)

__all__ = ["SchemaChangeService", "diff_schema", "validate_schema_definition"]
