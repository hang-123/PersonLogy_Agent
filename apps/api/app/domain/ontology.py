from enum import StrEnum


class ObjectType(StrEnum):
    COMPANY = "company"
    DEPARTMENT = "department"
    POSITION = "position"
    JD_VERSION = "jd_version"
    SKILL = "skill"
    EXPERIENCE = "experience"


class ObjectStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    INACTIVE = "inactive"
    UNKNOWN = "unknown"
    CLOSED = "closed"
    CURRENT = "current"
    HISTORICAL = "historical"
    DISPUTED = "disputed"
    MERGED = "merged"
    VERIFIED = "verified"
    ARCHIVED = "archived"


class EpistemicType(StrEnum):
    DIRECT_FACT = "direct_fact"
    SOURCE_ASSERTION = "source_assertion"
    DERIVED_INFERENCE = "derived_inference"
    PERSONAL_JUDGMENT = "personal_judgment"


class RelationStatus(StrEnum):
    CANDIDATE = "candidate"
    CONFIRMED = "confirmed"
    DISPUTED = "disputed"
    STALE = "stale"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"


class SourceType(StrEnum):
    TEXT = "text"
    WEB = "web"
    PDF = "pdf"
    MARKDOWN = "markdown"
    IMAGE = "image"
    OTHER = "other"


class SourceStatus(StrEnum):
    CAPTURED = "captured"
    PARSED = "parsed"
    PARSE_FAILED = "parse_failed"
    SOURCE_UNREACHABLE = "source_unreachable"
    ARCHIVED = "archived"


class EvidenceStatus(StrEnum):
    ACTIVE = "active"
    LOCATOR_INVALID = "locator_invalid"
    ARCHIVED = "archived"


class EvidenceDirection(StrEnum):
    SUPPORTS = "supports"
    REFUTES = "refutes"
    QUALIFIES = "qualifies"


class Visibility(StrEnum):
    PUBLIC = "public"
    PRIVATE = "private"
    SENSITIVE = "sensitive"


class ClaimStatus(StrEnum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    DISPUTED = "disputed"
    NEEDS_REVIEW = "needs_review"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"


class DecisionType(StrEnum):
    FOCUS_APPLY = "focus_apply"
    NORMAL_APPLY = "normal_apply"
    DEFER = "defer"
    ABANDON = "abandon"
    PREPARE = "prepare"


class DecisionStatus(StrEnum):
    PROPOSED = "proposed"
    CONFIRMED = "confirmed"
    REVISED = "revised"
    ABANDONED = "abandoned"
    COMPLETED = "completed"
    NEEDS_REVIEW = "needs_review"
    ARCHIVED = "archived"


class CandidateKind(StrEnum):
    OBJECT = "object"
    ATTRIBUTE = "attribute"
    RELATION = "relation"
    CLAIM = "claim"
    EVIDENCE = "evidence"


class CandidateStatus(StrEnum):
    PENDING_REVIEW = "pending_review"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    MERGED = "merged"


class BasisKind(StrEnum):
    CLAIM = "claim"
    RELATION = "relation"
    PREFERENCE = "preference"


class AggregateKind(StrEnum):
    OBJECT = "object"
    RELATION = "relation"
    SOURCE_DOCUMENT = "source_document"
    EVIDENCE = "evidence"
    CLAIM = "claim"
    DECISION = "decision"
    CANDIDATE = "candidate"


class FreshnessStatus(StrEnum):
    FRESH = "fresh"
    VERIFICATION_DUE = "verification_due"
    STALE = "stale"
    SOURCE_UNREACHABLE = "source_unreachable"
    SUPERSEDED = "superseded"


class JobType(StrEnum):
    SOURCE_PARSE = "source_parse"
    LLM_EXTRACT = "llm_extract"
    IMPACT_ANALYSIS = "impact_analysis"
    GRAPH_PROJECTION = "graph_projection"
    GRAPH_VALIDATION = "graph_validation"
    GRAPH_REBUILD = "graph_rebuild"


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ProjectionEventType(StrEnum):
    PUBLISH = "publish"
    REVISE = "revise"
    ARCHIVE = "archive"
    RESTORE = "restore"


class ProjectionStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DEGRADED = "degraded"


OBJECT_STATUS_POLICY: dict[ObjectType, frozenset[ObjectStatus]] = {
    ObjectType.COMPANY: frozenset(
        {ObjectStatus.ACTIVE, ObjectStatus.INACTIVE, ObjectStatus.ARCHIVED}
    ),
    ObjectType.DEPARTMENT: frozenset(
        {ObjectStatus.ACTIVE, ObjectStatus.UNKNOWN, ObjectStatus.ARCHIVED}
    ),
    ObjectType.POSITION: frozenset(
        {
            ObjectStatus.DRAFT,
            ObjectStatus.ACTIVE,
            ObjectStatus.CLOSED,
            ObjectStatus.UNKNOWN,
            ObjectStatus.ARCHIVED,
        }
    ),
    ObjectType.JD_VERSION: frozenset(
        {
            ObjectStatus.CURRENT,
            ObjectStatus.HISTORICAL,
            ObjectStatus.DISPUTED,
            ObjectStatus.ARCHIVED,
        }
    ),
    ObjectType.SKILL: frozenset(
        {ObjectStatus.ACTIVE, ObjectStatus.MERGED, ObjectStatus.ARCHIVED}
    ),
    ObjectType.EXPERIENCE: frozenset(
        {ObjectStatus.DRAFT, ObjectStatus.VERIFIED, ObjectStatus.ARCHIVED}
    ),
}


class DomainValidationError(ValueError):
    """Raised when a command violates the P0 ontology."""


def validate_object_status(object_type: ObjectType, status: ObjectStatus) -> None:
    allowed = OBJECT_STATUS_POLICY[object_type]
    if status not in allowed:
        allowed_values = ", ".join(sorted(item.value for item in allowed))
        raise DomainValidationError(
            f"{status.value!r} is invalid for {object_type.value}; allowed: {allowed_values}"
        )
