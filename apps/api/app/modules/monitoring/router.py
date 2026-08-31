from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse
from personlogy.adapters.telemetry import PrometheusMetricsExporter
from personlogy.application.monitoring import MetricsView, MonitoringHealth, MonitoringService

from app.modules.monitoring.schemas import (
    MetricSnapshotResponse,
    MetricsResponse,
    MonitoringHealthResponse,
    ProjectionFailureResponse,
)
from app.runtime import monitoring_service

router = APIRouter(tags=["monitoring"])


def _require_service() -> MonitoringService:
    if monitoring_service is None:
        raise HTTPException(status_code=503, detail="monitoring storage is not configured")
    return monitoring_service


def _metrics_response(view: MetricsView) -> MetricsResponse:
    return MetricsResponse(
        checkpoint=view.checkpoint,
        snapshots=[
            MetricSnapshotResponse(
                metric_name=snapshot.metric_name,
                value=snapshot.value,
                tags=dict(snapshot.tags),
                captured_at=snapshot.captured_at,
            )
            for snapshot in view.snapshots
        ],
        projection_failures=[
            ProjectionFailureResponse(
                sequence=failure.sequence,
                error_digest=failure.error_digest,
                attempts=failure.attempts,
                failed_at=failure.failed_at,
            )
            for failure in view.failures
        ],
    )


def health_response(health: MonitoringHealth) -> MonitoringHealthResponse:
    return MonitoringHealthResponse(
        status=health.status,
        generated_at=health.generated_at,
        queue_backlog=health.queue_backlog,
        queue_degraded_threshold=health.queue_degraded_threshold,
        index_latest_success_at=health.index.latest_success_at,
        index_latest_version=health.index.latest_version,
        index_age_seconds=health.index.age_seconds,
        index_stale=health.index.stale,
        database_ready=health.database_ready,
        audit_chain_valid=health.audit_chain.valid,
        audit_events_checked=health.audit_chain.checked_events,
        projection_checkpoint=health.projection_checkpoint,
        projection_failure_count=len(health.projection_failures),
        job_failure_rate=health.job_failure_rate,
        tool_unknown_state_total=health.tool_unknown_state_total,
    )


@router.get("/metrics", response_model=MetricsResponse)
async def get_metrics(
    metric_name: str | None = None,
    limit: int = Query(default=1000, ge=1, le=5000),
) -> MetricsResponse:
    view = await _require_service().metrics(metric_name=metric_name, limit=limit)
    return _metrics_response(view)


@router.get("/metrics/prometheus", response_class=PlainTextResponse)
async def get_metrics_prometheus(
    metric_name: str | None = None,
    limit: int = Query(default=5000, ge=1, le=5000),
) -> PlainTextResponse:
    view = await _require_service().metrics(metric_name=metric_name, limit=limit)
    return PlainTextResponse(PrometheusMetricsExporter().render(view.snapshots))


__all__ = ["health_response", "router"]
