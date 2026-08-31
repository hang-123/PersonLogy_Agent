"""Provider-independent contracts for audited tool execution."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field, replace
from typing import Protocol
from uuid import uuid4

from personlogy.domain.audit import digest_for
from personlogy.shared.errors import DomainValidationError

TOOL_RISK_CLASSES = frozenset(
    {"read", "write", "external_side_effect", "schema_migration", "secret_access"}
)
ToolCallable = Callable[[Mapping[str, object]], Awaitable[object]]


@dataclass(frozen=True, slots=True)
class ToolIntent:
    """An in-memory tool request; raw arguments are never sent to the auditor."""

    tool_name: str
    arguments: Mapping[str, object] = field(default_factory=dict)
    risk_class: str = "read"
    tool_version: str = "1.0"
    actor_type: str = "system"
    actor_id: str | None = None
    invocation_id: str = field(default_factory=lambda: f"tool-{uuid4().hex}")

    def __post_init__(self) -> None:
        if not self.tool_name.strip() or not self.tool_version.strip():
            raise DomainValidationError("tool name and version are required")
        if self.risk_class not in TOOL_RISK_CLASSES:
            raise DomainValidationError("unsupported tool risk class")
        if not self.actor_type.strip() or not self.invocation_id.strip():
            raise DomainValidationError("tool actor and invocation ID are required")
        if not isinstance(self.arguments, Mapping):
            raise DomainValidationError("tool arguments must be a mapping")
        object.__setattr__(self, "arguments", dict(self.arguments))

    def audit_view(self) -> ToolIntent:
        """Return an intent containing only a digest of the raw arguments."""

        return replace(self, arguments={"args_digest": digest_for(self.arguments)})


@dataclass(frozen=True, slots=True)
class AuditDecision:
    decision: str
    risk_level: str = "normal"
    reasons: tuple[str, ...] = ()
    violated_policies: tuple[str, ...] = ()
    required_checks: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.decision not in {"allow", "deny", "review"}:
            raise DomainValidationError("invalid audit decision")
        if not self.risk_level.strip():
            raise DomainValidationError("audit decision risk level is required")
        for field_name in ("reasons", "violated_policies", "required_checks"):
            value = tuple(getattr(self, field_name))
            if not all(isinstance(item, str) for item in value):
                raise DomainValidationError(f"{field_name} must contain strings")
            object.__setattr__(self, field_name, value)


class AuditorProvider(Protocol):
    """A no-tool provider used only for structured audit review."""

    async def review(
        self,
        *,
        intent: ToolIntent,
        context: Mapping[str, object],
    ) -> AuditDecision: ...


class ToolExecutor(Protocol):
    async def execute(self, intent: ToolIntent, tool: ToolCallable) -> object: ...


__all__ = [
    "TOOL_RISK_CLASSES",
    "AuditDecision",
    "AuditorProvider",
    "ToolCallable",
    "ToolExecutor",
    "ToolIntent",
]
