from uuid import uuid4

import pytest

from app.domain.ontology import (
    DomainValidationError,
    ObjectStatus,
    ObjectType,
    validate_object_status,
)
from app.domain.relations import RelationType, assert_acyclic_dependency, validate_relation


def test_requires_accepts_jd_version_to_skill_with_evidence() -> None:
    spec = validate_relation(
        RelationType.REQUIRES,
        ObjectType.JD_VERSION,
        ObjectType.SKILL,
        evidence_count=1,
    )

    assert spec.relation_type is RelationType.REQUIRES


def test_relation_rejects_invalid_endpoint_types() -> None:
    with pytest.raises(DomainValidationError, match="allowed source: department"):
        validate_relation(
            RelationType.OFFERS,
            ObjectType.SKILL,
            ObjectType.POSITION,
            evidence_count=1,
        )


def test_key_relation_rejects_missing_evidence() -> None:
    with pytest.raises(DomainValidationError, match="requires at least one evidence"):
        validate_relation(
            RelationType.REQUIRES,
            ObjectType.JD_VERSION,
            ObjectType.SKILL,
            evidence_count=0,
        )


def test_object_status_policy_rejects_cross_type_status() -> None:
    with pytest.raises(DomainValidationError, match="invalid for company"):
        validate_object_status(ObjectType.COMPANY, ObjectStatus.CURRENT)


def test_dependency_cycle_is_rejected_with_path() -> None:
    claim_a = uuid4()
    claim_b = uuid4()
    dependencies = {claim_a: {claim_b}}

    with pytest.raises(DomainValidationError, match="dependency cycle detected"):
        assert_acyclic_dependency(claim_b, claim_a, dependencies)


def test_dependency_without_back_path_is_allowed() -> None:
    claim_a = uuid4()
    claim_b = uuid4()
    claim_c = uuid4()

    assert_acyclic_dependency(claim_c, claim_a, {claim_a: {claim_b}})
