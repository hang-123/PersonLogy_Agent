from fastapi import APIRouter

from app.api.routes.health import router as health_router
from app.modules.conversations.router import router as conversations_router
from app.modules.governance.router import router as governance_router
from app.modules.jobs.router import router as jobs_router
from app.modules.pdfs.router import router as pdfs_router

api_router = APIRouter()
api_router.include_router(health_router, prefix="/health", tags=["health"])
api_router.include_router(conversations_router)
api_router.include_router(pdfs_router)
api_router.include_router(jobs_router)
api_router.include_router(governance_router)
