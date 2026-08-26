from fastapi import APIRouter

from app.api.routes.health import router as health_router
from app.modules.jobs.router import router as jobs_router

api_router = APIRouter()
api_router.include_router(health_router, prefix="/health", tags=["health"])
api_router.include_router(jobs_router)
