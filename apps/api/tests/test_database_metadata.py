import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from app.infrastructure.postgres.models import Base, Candidate, KnowledgeRelation

EXPECTED_TABLES = {
    "audit_log",
    "candidate",
    "claim",
    "claim_basis",
    "decision",
    "decision_basis",
    "evidence",
    "evidence_link",
    "graph_projection_checkpoint",
    "graph_projection_event",
    "knowledge_object",
    "knowledge_relation",
    "object_version",
    "processing_job",
    "source_document",
}


def test_authoritative_schema_registers_all_core_tables() -> None:
    assert set(Base.metadata.tables) == EXPECTED_TABLES
    assert all(table.primary_key.columns for table in Base.metadata.tables.values())


def test_relation_endpoints_reference_knowledge_objects() -> None:
    relation = KnowledgeRelation.__table__
    targets = {
        foreign_key.target_fullname
        for column_name in ("source_object_id", "target_object_id")
        for foreign_key in relation.c[column_name].foreign_keys
    }
    assert targets == {"knowledge_object.id"}


def test_relation_values_are_persisted_as_domain_values() -> None:
    relation_type = KnowledgeRelation.__table__.c.relation_type.type
    assert isinstance(relation_type, sa.Enum)
    assert set(relation_type.enums) == {
        "has_department",
        "offers",
        "has_version",
        "supersedes",
        "requires",
        "prefers",
        "demonstrates",
    }


def test_candidate_payload_uses_postgresql_jsonb() -> None:
    assert isinstance(Candidate.__table__.c.payload.type, JSONB)


def test_projection_event_has_idempotency_constraint() -> None:
    table = Base.metadata.tables["graph_projection_event"]
    unique_names = {
        constraint.name
        for constraint in table.constraints
        if isinstance(constraint, sa.UniqueConstraint)
    }
    assert "uq_graph_projection_event_idempotency" in unique_names
