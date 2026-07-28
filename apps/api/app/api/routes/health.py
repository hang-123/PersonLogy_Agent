from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from app import __version__
from app.core.config import get_settings

router = APIRouter()


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    version: str
    environment: str


@router.get("/live", response_model=HealthResponse)
def liveness() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        service="person-knowledge-api",
        version=__version__,
        environment=settings.environment,
    )


@router.get("/ready", response_model=HealthResponse)
def readiness() -> HealthResponse:
    # Database and projection checks are added with M1 repositories.
    return liveness()
