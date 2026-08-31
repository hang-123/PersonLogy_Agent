from fastapi import APIRouter

from app.api.routes.health import router as health_router
from app.modules.conversations.router import router as conversations_router
from app.modules.governance.router import router as governance_router
from app.modules.jobs.router import router as jobs_router
from app.modules.lineage.router import router as lineage_router
from app.modules.monitoring.router import router as monitoring_router
from app.modules.pdfs.router import router as pdfs_router
from app.modules.replay.router import router as replay_router
from app.modules.retrieval.router import router as retrieval_router
from app.modules.schema_management.router import router as schema_management_router
from app.modules.sources.router import router as sources_router

api_router = APIRouter()
api_router.include_router(health_router, prefix="/health", tags=["health"])
api_router.include_router(conversations_router)
api_router.include_router(pdfs_router)
api_router.include_router(jobs_router)
api_router.include_router(governance_router)
api_router.include_router(retrieval_router)
api_router.include_router(sources_router)
api_router.include_router(lineage_router)
api_router.include_router(monitoring_router)
api_router.include_router(replay_router)
api_router.include_router(schema_management_router)
