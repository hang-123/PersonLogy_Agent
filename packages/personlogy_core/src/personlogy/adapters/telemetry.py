"""Optional OpenTelemetry and dependency-free Prometheus bridges for P10."""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from importlib import import_module
from typing import Any

from personlogy.domain.audit import AuditEvent
from personlogy.domain.metrics import MetricSnapshot
from personlogy.shared.trace import TraceContext

_PROM_INVALID = re.compile(r"[^a-zA-Z0-9_:]")


def _otel_tracer() -> Any:
    try:
        trace = import_module("opentelemetry.trace")
    except ImportError as error:  # pragma: no cover - depends on deployment extras
        raise RuntimeError(
            "OpenTelemetry trace export requires the 'opentelemetry-api' package"
        ) from error
    return trace.get_tracer("personlogy")


def _otel_meter() -> Any:
    try:
        metrics = import_module("opentelemetry.metrics")
    except ImportError as error:  # pragma: no cover - depends on deployment extras
        raise RuntimeError(
            "OpenTelemetry metrics export requires the 'opentelemetry-api' package"
        ) from error
    return metrics.get_meter("personlogy")


def _otel_name(metric_name: str) -> str:
    normalized = _PROM_INVALID.sub("_", metric_name).lower()
    return f"personlogy_{normalized}"[:255]


class OpenTelemetryTraceExporter:
    """Map P10 trace contexts/events to an injected or global OTel tracer."""

    def __init__(self, tracer: Any | None = None) -> None:
        self._tracer = tracer or _otel_tracer()

    @contextmanager
    def span(
        self,
        name: str,
        *,
        context: TraceContext | None = None,
        attributes: Mapping[str, Any] | None = None,
    ) -> Iterator[Any]:
        active = context or TraceContext.current_or_root()
        span_attributes: dict[str, Any] = {
            "personlogy.trace_id": active.trace_id,
            "personlogy.span_id": active.span_id,
            "personlogy.parent_span_id": active.parent_span_id or "",
            "personlogy.request_id": active.request_id or "",
            "personlogy.actor_type": active.actor_type,
        }
        if active.actor_id is not None:
            span_attributes["personlogy.actor_id"] = active.actor_id
        if attributes:
            span_attributes.update(attributes)

        if hasattr(self._tracer, "start_as_current_span"):
            with self._tracer.start_as_current_span(
                name, attributes=span_attributes
            ) as span:
                yield span
            return

        span = self._tracer.start_span(name, attributes=span_attributes)
        try:
            yield span
        finally:
            span.end()

    def export_event(self, event: AuditEvent) -> None:
        """Emit a short-lived span carrying only bounded audit envelope fields."""

        attributes: dict[str, Any] = {
            "personlogy.event_type": event.event_type,
            "personlogy.status": event.status,
            "personlogy.entity_type": event.entity_type,
            "personlogy.entity_id": event.entity_id or "",
            "personlogy.reason_code": event.reason_code or "",
        }
        if event.sequence is not None:
            attributes["personlogy.audit_sequence"] = event.sequence
        with self.span(
            f"personlogy.audit.{event.event_type}",
            context=TraceContext(
                trace_id=event.trace_id,
                span_id=event.span_id or TraceContext.new_id("span"),
                parent_span_id=event.parent_span_id,
                request_id=event.request_id,
                actor_type=event.actor_type,
                actor_id=event.actor_id,
            ),
            attributes=attributes,
        ) as span:
            if hasattr(span, "set_status") and event.status in {"failed", "denied"}:
                try:
                    trace_api = import_module("opentelemetry.trace")
                    span.set_status(
                        trace_api.Status(
                            trace_api.StatusCode.ERROR,
                            event.reason_code or event.status,
                        )
                    )
                except ImportError:  # pragma: no cover - exercised with injected fakes
                    span.set_status("ERROR", event.reason_code or event.status)


class PrometheusMetricsExporter:
    """Render P10 snapshots as Prometheus text without a hard SDK dependency."""

    @staticmethod
    def _name(metric_name: str) -> str:
        normalized = _PROM_INVALID.sub("_", metric_name).lower()
        return f"personlogy_{normalized}"

    @staticmethod
    def _label(value: str) -> str:
        return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')

    def render(self, snapshots: Iterable[MetricSnapshot]) -> str:
        latest: dict[tuple[str, tuple[tuple[str, str], ...]], MetricSnapshot] = {}
        for snapshot in snapshots:
            latest[(snapshot.metric_name, tuple(sorted(snapshot.tags.items())))] = snapshot
        grouped: dict[str, list[MetricSnapshot]] = {}
        for snapshot in latest.values():
            grouped.setdefault(self._name(snapshot.metric_name), []).append(snapshot)

        lines: list[str] = []
        for name in sorted(grouped):
            metric_type = "counter" if name.endswith("_total") else "gauge"
            lines.append(f"# TYPE {name} {metric_type}")
            for snapshot in sorted(grouped[name], key=lambda item: tuple(sorted(item.tags))):
                labels = ""
                if snapshot.tags:
                    labels = "{" + ",".join(
                        f'{key}="{self._label(value)}"'
                        for key, value in sorted(snapshot.tags.items())
                    ) + "}"
                timestamp = int(snapshot.captured_at.timestamp() * 1000)
                lines.append(f"{name}{labels} {snapshot.value:.17g} {timestamp}")
        return "\n".join(lines) + ("\n" if lines else "")


class OpenTelemetryMetricsExporter:
    """Expose current P10 snapshots through OTel observable gauges.

    Snapshot values are gauges, even when their names end in ``_total``: the
    event projector owns accumulation and this adapter must not double-count
    when a snapshot is exported more than once.
    """

    def __init__(self, meter: Any | None = None) -> None:
        self._meter = meter or _otel_meter()
        self._latest: dict[str, dict[tuple[tuple[str, str], ...], MetricSnapshot]] = {}
        self._instruments: dict[str, Any] = {}

    def export(self, snapshots: Iterable[MetricSnapshot]) -> int:
        for snapshot in snapshots:
            name = _otel_name(snapshot.metric_name)
            self._latest.setdefault(name, {})[
                tuple(sorted(snapshot.tags.items()))
            ] = snapshot
            if name in self._instruments:
                continue

            def callback(_options: Any = None, *, metric_name: str = name) -> tuple[Any, ...]:
                current = self._latest.get(metric_name, {})
                if not current:
                    return ()
                try:
                    observation_type = import_module("opentelemetry.metrics").Observation
                except ImportError as error:  # pragma: no cover
                    raise RuntimeError(
                        "OpenTelemetry metrics export requires 'opentelemetry-api'"
                    ) from error
                return tuple(
                    observation_type(snapshot.value, attributes=dict(snapshot.tags))
                    for snapshot in current.values()
                )

            self._instruments[name] = self._meter.create_observable_gauge(
                name,
                callbacks=[callback],
                description="PersonLogy projected P10 metric snapshot",
            )
        return len(self._instruments)


__all__ = [
    "OpenTelemetryMetricsExporter",
    "OpenTelemetryTraceExporter",
    "PrometheusMetricsExporter",
]
