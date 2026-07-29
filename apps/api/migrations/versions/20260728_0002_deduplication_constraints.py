"""Add canonical deduplication constraints.

Revision ID: 20260728_0002
Revises: 20260728_0001
Create Date: 2026-07-28
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260728_0002"
down_revision: str | None = "20260728_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_knowledge_object_canonical",
        "knowledge_object",
        ["object_type", "canonical_name"],
    )
    op.create_unique_constraint(
        "uq_knowledge_relation_semantics",
        "knowledge_relation",
        ["source_object_id", "relation_type", "target_object_id"],
    )
    op.drop_index("ix_source_document_fingerprint", table_name="source_document")
    op.create_unique_constraint(
        "uq_source_document_fingerprint",
        "source_document",
        ["content_fingerprint"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_source_document_fingerprint",
        "source_document",
        type_="unique",
    )
    op.create_index(
        "ix_source_document_fingerprint",
        "source_document",
        ["content_fingerprint"],
    )
    op.drop_constraint(
        "uq_knowledge_relation_semantics",
        "knowledge_relation",
        type_="unique",
    )
    op.drop_constraint(
        "uq_knowledge_object_canonical",
        "knowledge_object",
        type_="unique",
    )
