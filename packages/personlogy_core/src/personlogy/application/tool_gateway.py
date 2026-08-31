"""Fail-closed audited tool gateway."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Collection, Mapping
from dataclasses import dataclass

from personlogy.application.audit import append_audit_event
from personlogy.domain.audit import digest_for
from personlogy.ports.audit import AuditSink
from personlogy.ports.tools import (
    AuditDecision,
    AuditorProvider,
    ToolCallable,
    ToolIntent,
)
from personlogy.shared.errors import DomainValidationError
from personlogy.shared.trace import TraceContext

AuditorReview = Callable[..., Awaitable[AuditDecision]]


class ToolDeniedError(DomainValidationError):
    """Raised when a tool cannot pass the audit and policy gates."""


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    allowed: bool
    reason_code: str
    violated_policies: tuple[str, ...] = ()


class AuditPolicyEngine:
    """Deterministic final gate; an auditor cannot override its hard rules."""

    def __init__(
        self,
        *,
        allowed_risk_classes: Collection[str] | None = None,
        blocked_tools: Collection[str] = (),
        policy_version: str = "1.0",
    ) -> None:
        self._allowed_risk_classes = frozenset(
            allowed_risk_classes
            if allowed_risk_classes is not None
            else {"read", "write", "external_side_effect", "schema_migration", "secret_access"}
        )
        self._blocked_tools = frozenset(blocked_tools)
        self.policy_version = policy_version

    def evaluate(self, intent: ToolIntent, decision: AuditDecision) -> PolicyDecision:
        if intent.tool_name in self._blocked_tools:
            return PolicyDecision(False, "tool_blocked", ("blocked_tool",))
        if intent.risk_class not in self._allowed_risk_classes:
            return PolicyDecision(False, "risk_class_not_allowed", ("risk_class",))
        if decision.violated_policies:
            return PolicyDecision(False, "auditor_policy_violation", decision.violated_policies)
        if decision.decision != "allow":
            return PolicyDecision(False, f"auditor_{decision.decision}")
        return PolicyDecision(True, "allowed")


class CallableAuditorProvider:
    """Adapter for a no-tool structured auditor callback."""

    def __init__(self, review: AuditorReview) -> None:
        self._review = review

    async def review(
        self,
        *,
        intent: ToolIntent,
        context: Mapping[str, object],
    ) -> AuditDecision:
        decision = await self._review(intent=intent, context=context)
        if not isinstance(decision, AuditDecision):
            raise DomainValidationError("auditor returned an invalid decision")
        return decision


class AuditedToolExecutor:
    """The single execution path for tools, including preflight and postflight."""

    def __init__(
        self,
        audit_sink: AuditSink,
        auditor_provider: AuditorProvider,
        policy_engine: AuditPolicyEngine,
    ) -> None:
        self._audit_sink = audit_sink
        self._auditor_provider = auditor_provider
        self._policy_engine = policy_engine

    async def execute(self, intent: ToolIntent, tool: ToolCallable) -> object:
        parent = TraceContext.current_or_root()
        context = TraceContext(
            trace_id=parent.trace_id,
            span_id=TraceContext.new_id("span"),
            parent_span_id=parent.span_id,
            request_id=parent.request_id,
            actor_type=intent.actor_type,
            actor_id=intent.actor_id,
        )
        entity_id = intent.invocation_id
        metadata = {
            "tool_invocation_id": entity_id,
            "tool_name": intent.tool_name,
            "tool_version": intent.tool_version,
            "risk_class": intent.risk_class,
            "args_digest": digest_for(intent.arguments),
        }
        await append_audit_event(
            self._audit_sink,
            event_type="tool.requested",
            status="requested",
            entity_type="tool_invocation",
            entity_id=entity_id,
            context=context,
            metadata=metadata,
        )

        audit_context: Mapping[str, object] = {
            "trace_id": context.trace_id,
            "request_id": context.request_id,
            "actor_type": context.actor_type,
            "actor_id_digest": digest_for(context.actor_id) if context.actor_id else None,
            "tool_invocation_id": entity_id,
            "risk_class": intent.risk_class,
        }
        auditor_context = context.child()
        await append_audit_event(
            self._audit_sink,
            event_type="auditor.review.started",
            status="started",
            entity_type="tool_invocation",
            entity_id=entity_id,
            context=auditor_context,
            metadata={**metadata, "auditor_span_id": auditor_context.span_id},
        )
        try:
            with auditor_context.activate():
                decision = await self._auditor_provider.review(
                    intent=intent.audit_view(),
                    context=audit_context,
                )
            if not isinstance(decision, AuditDecision):
                raise DomainValidationError("auditor returned an invalid decision")
        except Exception as error:
            await append_audit_event(
                self._audit_sink,
                event_type="auditor.review.failed",
                status="failed",
                entity_type="tool_invocation",
                entity_id=entity_id,
                context=auditor_context,
                reason_code="auditor_failure",
                metadata={**metadata, "error_digest": digest_for(str(error))},
            )
            await self._deny(
                intent,
                context,
                reason_code="audit_unavailable",
                metadata=metadata,
            )
            raise ToolDeniedError("tool denied because audit review failed") from error

        await append_audit_event(
            self._audit_sink,
            event_type="auditor.review.succeeded",
            status="succeeded",
            entity_type="tool_invocation",
            entity_id=entity_id,
            context=auditor_context,
            metadata={
                **metadata,
                "auditor_span_id": auditor_context.span_id,
                "decision": decision.decision,
                "risk_level": decision.risk_level,
                "required_checks_digest": digest_for(decision.required_checks),
                "violated_policies_digest": digest_for(decision.violated_policies),
                "policy_version": self._policy_engine.policy_version,
            },
        )
        policy = self._policy_engine.evaluate(intent, decision)
        if not policy.allowed:
            await self._deny(
                intent,
                context,
                reason_code=policy.reason_code,
                metadata={
                    **metadata,
                    "decision": decision.decision,
                    "policy_version": self._policy_engine.policy_version,
                    "violated_policies_digest": digest_for(policy.violated_policies),
                },
            )
            raise ToolDeniedError(f"tool denied: {policy.reason_code}")

        await append_audit_event(
            self._audit_sink,
            event_type="tool.started",
            status="started",
            entity_type="tool_invocation",
            entity_id=entity_id,
            context=context,
            metadata=metadata,
        )
        try:
            with context.activate():
                result = await tool(intent.arguments)
        except Exception as error:
            await append_audit_event(
                self._audit_sink,
                event_type="tool.failed",
                status="failed",
                entity_type="tool_invocation",
                entity_id=entity_id,
                context=context,
                reason_code="tool_failure",
                metadata={**metadata, "error_digest": digest_for(str(error))},
            )
            raise
        await append_audit_event(
            self._audit_sink,
            event_type="tool.succeeded",
            status="succeeded",
            entity_type="tool_invocation",
            entity_id=entity_id,
            context=context,
            metadata={**metadata, "result_digest": digest_for(result)},
        )
        return result

    async def _deny(
        self,
        intent: ToolIntent,
        context: TraceContext,
        *,
        reason_code: str,
        metadata: Mapping[str, object],
    ) -> None:
        await append_audit_event(
            self._audit_sink,
            event_type="tool.denied",
            status="denied",
            entity_type="tool_invocation",
            entity_id=intent.invocation_id,
            context=context,
            reason_code=reason_code,
            metadata=metadata,
        )


class ToolGateway(AuditedToolExecutor):
    """Named façade preserving one audited entry point for all tools."""


__all__ = [
    "AuditPolicyEngine",
    "AuditedToolExecutor",
    "CallableAuditorProvider",
    "PolicyDecision",
    "ToolDeniedError",
    "ToolGateway",
]
