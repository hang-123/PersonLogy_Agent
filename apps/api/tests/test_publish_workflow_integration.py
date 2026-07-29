import os

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.application.errors import ConflictError
from app.domain.ontology import (
    AggregateKind,
    CandidateKind,
    CandidateStatus,
    DomainValidationError,
    ObjectType,
)
from app.infrastructure.postgres.models import (
    AuditLog,
    Candidate,
    EvidenceLink,
    GraphProjectionEvent,
    KnowledgeObject,
    KnowledgeRelation,
    ObjectVersion,
)
from app.modules.ingestion.schemas import EvidenceCreate, SourceCreate
from app.modules.ingestion.service import (
    create_evidence,
    create_source,
    list_sources,
)
from app.modules.knowledge.service import list_objects
from app.modules.review.schemas import (
    AcceptCandidateRequest,
    CandidateCreate,
    MergeCandidateRequest,
)
from app.modules.review.service import (
    accept_candidate,
    create_candidate,
    merge_candidate,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def database_session() -> Session:
    database_url = os.getenv("PKS_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("PKS_TEST_DATABASE_URL is not configured")

    database_name = make_url(database_url).database or ""
    if not database_name.endswith("_test"):
        pytest.fail("integration tests require a database name ending in '_test'")

    engine = sa.create_engine(database_url, pool_pre_ping=True)
    connection = engine.connect()
    outer_transaction = connection.begin()
    session = Session(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    try:
        yield session
    finally:
        session.close()
        outer_transaction.rollback()
        connection.close()
        engine.dispose()


def test_source_evidence_candidate_publish_is_atomic(
    database_session: Session,
) -> None:
    source = create_source(
        database_session,
        SourceCreate(
            title="Backend Engineer JD",
            source_type="text",
            source_url="https://example.test/jobs/backend",
            raw_text="Backend Engineer requires Python.",
            created_by="integration-test",
        ),
    )
    evidence = create_evidence(
        database_session,
        source.id,
        EvidenceCreate(
            excerpt="Backend Engineer requires Python.",
            locator={"paragraph": 1},
            source_level="L1",
            created_by="integration-test",
        ),
    )
    source_id = source.id
    evidence_id = evidence.id

    jd_candidate = create_candidate(
        database_session,
        CandidateCreate(
            candidate_kind=CandidateKind.OBJECT,
            source_document_id=source_id,
            created_by="integration-test",
            payload={
                "object_type": "jd_version",
                "canonical_name": "backend-engineer-jd-integration",
                "display_name": "Backend Engineer JD",
                "status": "current",
            },
        ),
    )
    skill_candidate = create_candidate(
        database_session,
        CandidateCreate(
            candidate_kind=CandidateKind.OBJECT,
            source_document_id=source_id,
            created_by="integration-test",
            payload={
                "object_type": "skill",
                "canonical_name": "python-integration",
                "display_name": "Python",
                "status": "active",
            },
        ),
    )
    review = AcceptCandidateRequest(
        reviewed_by="integration-reviewer",
        reason="verified against source",
    )
    jd_result = accept_candidate(database_session, jd_candidate.id, review)
    skill_result = accept_candidate(database_session, skill_candidate.id, review)

    merge_source_candidate = create_candidate(
        database_session,
        CandidateCreate(
            candidate_kind=CandidateKind.OBJECT,
            source_document_id=source_id,
            created_by="integration-test",
            payload={
                "object_type": "skill",
                "canonical_name": "py-thon-integration",
                "display_name": "Py Thon",
                "status": "active",
            },
        ),
    )
    merge_result = merge_candidate(
        database_session,
        merge_source_candidate.id,
        MergeCandidateRequest(
            target_object_id=skill_result.target_id,
            reviewed_by="integration-reviewer",
            reason="normalized duplicate skill alias",
            aliases=["Python Language"],
        ),
    )
    assert merge_result.candidate_status is CandidateStatus.MERGED
    assert merge_result.target_version == 2

    missing_evidence_candidate = create_candidate(
        database_session,
        CandidateCreate(
            candidate_kind=CandidateKind.RELATION,
            source_document_id=source_id,
            created_by="integration-test",
            payload={
                "source_object_id": str(jd_result.target_id),
                "relation_type": "requires",
                "target_object_id": str(skill_result.target_id),
                "epistemic_type": "source_assertion",
                "status": "confirmed",
                "evidence_ids": [],
            },
        ),
    )
    missing_evidence_candidate_id = missing_evidence_candidate.id
    with pytest.raises(DomainValidationError, match="requires at least one evidence"):
        accept_candidate(database_session, missing_evidence_candidate_id, review)

    invalid_endpoint_candidate = create_candidate(
        database_session,
        CandidateCreate(
            candidate_kind=CandidateKind.RELATION,
            source_document_id=source_id,
            created_by="integration-test",
            payload={
                "source_object_id": str(skill_result.target_id),
                "relation_type": "offers",
                "target_object_id": str(jd_result.target_id),
                "epistemic_type": "source_assertion",
                "status": "confirmed",
                "evidence_ids": [str(evidence_id)],
            },
        ),
    )
    invalid_endpoint_candidate_id = invalid_endpoint_candidate.id
    with pytest.raises(DomainValidationError, match="is invalid"):
        accept_candidate(database_session, invalid_endpoint_candidate_id, review)

    relation_candidate = create_candidate(
        database_session,
        CandidateCreate(
            candidate_kind=CandidateKind.RELATION,
            source_document_id=source_id,
            created_by="integration-test",
            payload={
                "source_object_id": str(jd_result.target_id),
                "relation_type": "requires",
                "target_object_id": str(skill_result.target_id),
                "epistemic_type": "source_assertion",
                "status": "confirmed",
                "evidence_ids": [str(evidence_id)],
            },
        ),
    )
    relation_result = accept_candidate(
        database_session,
        relation_candidate.id,
        review,
    )

    assert relation_result.target_kind is AggregateKind.RELATION

    with pytest.raises(ConflictError, match="already accepted"):
        accept_candidate(database_session, relation_candidate.id, review)

    assert database_session.scalar(
        sa.select(sa.func.count()).select_from(KnowledgeObject)
    ) == 2
    assert database_session.scalar(
        sa.select(sa.func.count()).select_from(KnowledgeRelation)
    ) == 1
    assert database_session.scalar(
        sa.select(sa.func.count()).select_from(EvidenceLink)
    ) == 1
    assert database_session.scalar(
        sa.select(sa.func.count()).select_from(ObjectVersion)
    ) == 4
    assert database_session.scalar(
        sa.select(sa.func.count()).select_from(GraphProjectionEvent)
    ) == 4
    assert database_session.scalar(
        sa.select(sa.func.count()).select_from(AuditLog)
    ) == 12

    published_candidates = list(
        database_session.scalars(
            sa.select(Candidate).where(
                Candidate.id.in_(
                    [jd_candidate.id, skill_candidate.id, relation_candidate.id]
                )
            )
        )
    )
    assert {item.status for item in published_candidates} == {
        CandidateStatus.ACCEPTED
    }

    pending_candidates = list(
        database_session.scalars(
            sa.select(Candidate).where(
                Candidate.id.in_(
                    [missing_evidence_candidate_id, invalid_endpoint_candidate_id]
                )
            )
        )
    )
    assert {item.status for item in pending_candidates} == {
        CandidateStatus.PENDING_REVIEW
    }


    merged_candidate = database_session.get(Candidate, merge_source_candidate.id)
    merged_target = database_session.get(KnowledgeObject, skill_result.target_id)
    assert merged_candidate is not None
    assert merged_candidate.status is CandidateStatus.MERGED
    assert merged_target is not None
    assert merged_target.version == 2
    assert {"Py Thon", "py-thon-integration", "Python Language"} <= set(
        merged_target.aliases
    )


    matched_objects, object_total = list_objects(
        database_session,
        object_type=ObjectType.SKILL,
        query="Py Thon",
        include_archived=False,
        limit=20,
        offset=0,
    )
    matched_sources, source_total = list_sources(
        database_session,
        query="Backend Engineer",
        limit=20,
        offset=0,
    )
    assert object_total == 1
    assert [item.id for item in matched_objects] == [skill_result.target_id]
    assert source_total == 1
    assert [item.id for item in matched_sources] == [source_id]
