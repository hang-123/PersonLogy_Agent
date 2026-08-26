from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from app import __version__
from app.core.config import get_settings

router = APIRouter()


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    service: str
    version: str
    environment: str
    dependencies: dict[str, str]


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
def readiness() -> HealthResponse:
    settings = get_settings()
    dependencies = settings.dependency_status()
    storage_ready = settings.storage_backend != "gel"
    queue_ready = settings.queue_backend != "gel"
    status: Literal["ok", "degraded"] = "ok" if storage_ready and queue_ready else "degraded"
    return HealthResponse(
        status=status,
        service="person-knowledge-api",
        version=__version__,
        environment=settings.environment,
        dependencies=dependencies,
    )
