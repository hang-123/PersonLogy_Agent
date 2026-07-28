from collections.abc import Collection, Mapping
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from app.domain.ontology import DomainValidationError, ObjectType


class RelationType(StrEnum):
    HAS_DEPARTMENT = "has_department"
    OFFERS = "offers"
    HAS_VERSION = "has_version"
    SUPERSEDES = "supersedes"
    REQUIRES = "requires"
    PREFERS = "prefers"
    DEMONSTRATES = "demonstrates"


@dataclass(frozen=True, slots=True)
class RelationSpec:
    relation_type: RelationType
    source_types: frozenset[ObjectType]
    target_types: frozenset[ObjectType]
    requires_evidence: bool = True
    acyclic: bool = False


RELATION_SPECS: dict[RelationType, RelationSpec] = {
    RelationType.HAS_DEPARTMENT: RelationSpec(
        RelationType.HAS_DEPARTMENT,
        frozenset({ObjectType.COMPANY}),
        frozenset({ObjectType.DEPARTMENT}),
    ),
    RelationType.OFFERS: RelationSpec(
        RelationType.OFFERS,
        frozenset({ObjectType.DEPARTMENT}),
        frozenset({ObjectType.POSITION}),
    ),
    RelationType.HAS_VERSION: RelationSpec(
        RelationType.HAS_VERSION,
        frozenset({ObjectType.POSITION}),
        frozenset({ObjectType.JD_VERSION}),
    ),
    RelationType.SUPERSEDES: RelationSpec(
        RelationType.SUPERSEDES,
        frozenset({ObjectType.JD_VERSION}),
        frozenset({ObjectType.JD_VERSION}),
        acyclic=True,
    ),
    RelationType.REQUIRES: RelationSpec(
        RelationType.REQUIRES,
        frozenset({ObjectType.JD_VERSION}),
        frozenset({ObjectType.SKILL}),
    ),
    RelationType.PREFERS: RelationSpec(
        RelationType.PREFERS,
        frozenset({ObjectType.JD_VERSION}),
        frozenset({ObjectType.SKILL}),
    ),
    RelationType.DEMONSTRATES: RelationSpec(
        RelationType.DEMONSTRATES,
        frozenset({ObjectType.EXPERIENCE}),
        frozenset({ObjectType.SKILL}),
    ),
}


def validate_relation(
    relation_type: RelationType,
    source_type: ObjectType,
    target_type: ObjectType,
    *,
    evidence_count: int,
) -> RelationSpec:
    spec = RELATION_SPECS[relation_type]
    if source_type not in spec.source_types or target_type not in spec.target_types:
        allowed_sources = ", ".join(sorted(item.value for item in spec.source_types))
        allowed_targets = ", ".join(sorted(item.value for item in spec.target_types))
        raise DomainValidationError(
            f"{source_type.value} -[{relation_type.value}]-> {target_type.value} is invalid; "
            f"allowed source: {allowed_sources}; allowed target: {allowed_targets}"
        )
    if spec.requires_evidence and evidence_count < 1:
        raise DomainValidationError(f"{relation_type.value} requires at least one evidence item")
    return spec


def assert_acyclic_dependency(
    source_id: UUID,
    target_id: UUID,
    dependencies: Mapping[UUID, Collection[UUID]],
) -> None:
    """Reject adding source -> target when target already reaches source."""

    stack: list[tuple[UUID, tuple[UUID, ...]]] = [(target_id, (target_id,))]
    visited: set[UUID] = set()

    while stack:
        current, path = stack.pop()
        if current == source_id:
            cycle = " -> ".join(str(item) for item in (source_id, *path))
            raise DomainValidationError(f"dependency cycle detected: {cycle}")
        if current in visited:
            continue
        visited.add(current)
        for dependency_id in dependencies.get(current, ()):
            stack.append((dependency_id, (*path, dependency_id)))
