from pathlib import Path


def test_gel_schema_declares_provenance_and_job_invariants() -> None:
    schema = (Path(__file__).parents[3] / "GEL" / "dbschema" / "default.gel").read_text(
        encoding="utf-8"
    )

    assert "type Claim extending Timestamped" in schema
    assert "required multi citations: Citation" in schema
    assert "type Relation extending Timestamped" in schema
    assert "required source: KnowledgeNode" in schema
    assert "required target: KnowledgeNode" in schema
    assert "constraint exclusive" in schema
    assert "type Job extending Timestamped" in schema
    assert "required idempotency_key: str" in schema
