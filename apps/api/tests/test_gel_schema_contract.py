from pathlib import Path


def _schema() -> str:
    return (Path(__file__).parents[3] / "GEL" / "dbschema" / "default.gel").read_text(
        encoding="utf-8"
    )


def test_gel_schema_declares_provenance_and_job_invariants() -> None:
    schema = _schema()

    assert "type Claim extending Timestamped" in schema
    assert "required multi citations: Citation" in schema
    assert "type Relation extending Timestamped" in schema
    assert "required source: KnowledgeNode" in schema
    assert "required target: KnowledgeNode" in schema
    assert "constraint exclusive" in schema
    assert "type Job extending Timestamped" in schema
    assert "required idempotency_key: str" in schema


def test_gel_schema_declares_governance_and_compilation_contract() -> None:
    schema = _schema()

    # Governance objects (migration 00002)
    for type_name in (
        "GovernanceRun",
        "GovernanceIssue",
        "DuplicateGroup",
        "ConflictRecord",
        "ReviewTask",
    ):
        assert f"type {type_name} extending Timestamped" in schema

    # Governance enums
    for enum_name, members in (
        ("CandidateKind", "node, claim, relation"),
        ("ReviewTaskStatus", "pending, approved, rejected, revised"),
        ("GovernanceRunStatus", "passed, needs_review, rejected"),
        ("GovernanceIssueSeverity", "info, warning, error"),
    ):
        assert f"scalar type {enum_name} extending enum<{members}>" in schema

    # Compilation metadata / review status on knowledge objects
    assert "required metadata: json" in schema
    assert "required status: VerificationStatus" in schema
    assert (
        "scalar type VerificationStatus extending enum<candidate, machine_checked, "
        "pending_review, needs_revision, human_verified, ready_for_writeback, rejected>"
    ) in schema


def test_gel_schema_declares_p10f_audit_chain() -> None:
    schema = _schema()

    assert "type AuditEvent extending Timestamped" in schema
    assert "required sequence: int64" in schema
    assert "required event_hash: str" in schema
    assert "type AuditChainHead" in schema
    migration = _migration("00003-m1idqkc.edgeql")
    assert "CREATE TYPE default::AuditEvent" in migration
    assert "CREATE TYPE default::AuditChainHead" in migration


def _migration(name: str) -> str:
    return (Path(__file__).parents[3] / "GEL" / "dbschema" / "migrations" / name).read_text(
        encoding="utf-8"
    )


def test_gel_schema_declares_writeback_and_conversation_contract() -> None:
    schema = _schema()

    # Writeback objects (migration 00004)
    for type_name in ("WritebackRecord", "WritebackItem"):
        assert f"type {type_name} extending Timestamped" in schema
    assert (
        "scalar type WritebackStatus extending enum<effects_pending, retryable_failed, "
        "completed, reverted>"
    ) in schema
    assert "required idempotency_key: str" in schema

    # Conversation import objects (migration 00004)
    for type_name in ("Conversation", "ConversationMessage"):
        assert f"type {type_name} extending Timestamped" in schema
    assert "constraint exclusive on ((.project, .external_id))" in schema
    assert "constraint exclusive on ((.conversation, .external_id))" in schema

    migration = _migration("00004-m1srqqu.edgeql")
    assert "CREATE TYPE default::WritebackRecord" in migration
    assert "CREATE TYPE default::WritebackItem" in migration
    assert "CREATE TYPE default::Conversation" in migration
    assert "CREATE TYPE default::ConversationMessage" in migration
