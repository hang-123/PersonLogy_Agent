from fastapi import APIRouter

from app.api.routes.health import router as health_router
from app.modules.ingestion.router import router as ingestion_router
from app.modules.knowledge.router import router as knowledge_router
from app.modules.review.router import router as review_router

api_router = APIRouter()
api_router.include_router(health_router, prefix="/health", tags=["health"])

api_router.include_router(ingestion_router, tags=["ingestion"])
api_router.include_router(knowledge_router, tags=["knowledge"])
api_router.include_router(review_router, tags=["review"])
