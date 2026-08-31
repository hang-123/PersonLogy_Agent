"""Immutable metric snapshot and projection failure models."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime

from personlogy.shared.errors import DomainValidationError

_METRIC_NAME = re.compile(r"^[a-z][a-z0-9_.-]{1,127}$")
_TAG_NAME = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
_RESERVED_TAGS = frozenset({"trace_id", "request_id", "prompt", "query", "raw", "content"})
_MAX_TAGS = 4


@dataclass(frozen=True, slots=True)
class MetricSnapshot:
    """One low-cardinality aggregate value at a point in time."""

    metric_name: str
    value: float
    tags: Mapping[str, str] = field(default_factory=dict)
    captured_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not _METRIC_NAME.fullmatch(self.metric_name):
            raise DomainValidationError("metric name is invalid")
        if not math.isfinite(self.value):
            raise DomainValidationError("metric value must be finite")
        if self.captured_at.tzinfo is None or self.captured_at.utcoffset() is None:
            raise DomainValidationError("metric captured_at must be timezone-aware")
        if not isinstance(self.tags, Mapping) or len(self.tags) > _MAX_TAGS:
            raise DomainValidationError("metric tags must be a mapping with at most four fields")
        normalized: dict[str, str] = {}
        for key, value in self.tags.items():
            if (
                not isinstance(key, str)
                or not _TAG_NAME.fullmatch(key)
                or key in _RESERVED_TAGS
            ):
                raise DomainValidationError(f"metric tag name is not allowed: {key!r}")
            if not isinstance(value, str) or not value or len(value) > 64:
                raise DomainValidationError(
                    "metric tag values must be non-empty strings under 64 bytes"
                )
            normalized[key] = value
        object.__setattr__(self, "tags", normalized)


@dataclass(frozen=True, slots=True)
class ProjectionFailure:
    """A failed event projection that can be retried without skipping its sequence."""

    sequence: int
    error_digest: str
    attempts: int
    failed_at: datetime
    resolved_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.sequence < 1 or self.attempts < 1:
            raise DomainValidationError(
                "projection failure sequence and attempts must be positive"
            )
        if len(self.error_digest) != 64:
            raise DomainValidationError("projection failure digest is invalid")
        if self.failed_at.tzinfo is None or self.failed_at.utcoffset() is None:
            raise DomainValidationError(
                "projection failure timestamp must be timezone-aware"
            )


__all__ = ["MetricSnapshot", "ProjectionFailure"]
