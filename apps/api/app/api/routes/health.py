from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from app import __version__
from app.core.config import get_settings
from app.modules.monitoring.router import health_response
from app.modules.monitoring.schemas import MonitoringHealthResponse

router = APIRouter()


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    service: str
    version: str
    environment: str
    dependencies: dict[str, str]
    monitoring: MonitoringHealthResponse | None = None


@router.get("/live", response_model=HealthResponse)
def liveness() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        service="person-knowledge-api",
        version=__version__,
        environment=settings.environment,
        dependencies=settings.dependency_status(),
    )


@router.get("/ready", response_model=HealthResponse)
async def readiness() -> HealthResponse:
    settings = get_settings()
    dependencies = settings.dependency_status()
    gel_ready = True
    if settings.storage_backend == "gel" or settings.queue_backend == "gel":
        from app import runtime

        gel_ready = runtime.gel_store is not None and await runtime.gel_store.ping()
    storage_ready = settings.storage_backend != "gel" or gel_ready
    queue_ready = settings.queue_backend != "gel" or gel_ready
    monitoring: MonitoringHealthResponse | None = None
    monitoring_ready = True
    from app import runtime

    if runtime.monitoring_service is not None:
        monitoring_data = await runtime.monitoring_service.health()
        monitoring = health_response(monitoring_data)
        monitoring_ready = monitoring_data.status == "ok"
        dependencies = {**dependencies, "monitoring": monitoring_data.status}
    status: Literal["ok", "degraded"] = (
        "ok" if storage_ready and queue_ready and monitoring_ready else "degraded"
    )
    return HealthResponse(
        status=status,
        service="person-knowledge-api",
        version=__version__,
        environment=settings.environment,
        dependencies=dependencies,
        monitoring=monitoring,
    )
