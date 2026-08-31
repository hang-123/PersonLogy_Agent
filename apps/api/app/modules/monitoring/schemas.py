from datetime import datetime

from pydantic import BaseModel


class MetricSnapshotResponse(BaseModel):
    metric_name: str
    value: float
    tags: dict[str, str]
    captured_at: datetime


class ProjectionFailureResponse(BaseModel):
    sequence: int
    error_digest: str
    attempts: int
    failed_at: datetime


class MetricsResponse(BaseModel):
    checkpoint: int
    snapshots: list[MetricSnapshotResponse]
    projection_failures: list[ProjectionFailureResponse]


class MonitoringHealthResponse(BaseModel):
    status: str
    generated_at: datetime
    queue_backlog: int
    queue_degraded_threshold: int
    index_latest_success_at: datetime | None
    index_latest_version: int | None
    index_age_seconds: float | None
    index_stale: bool
    database_ready: bool
    audit_chain_valid: bool
    audit_events_checked: int
    projection_checkpoint: int
    projection_failure_count: int
    job_failure_rate: float
    tool_unknown_state_total: float
