from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from personlogy.shared.trace import TraceContext

from app import __version__, runtime
from app.api.errors import register_error_handlers
from app.api.router import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    structlog.get_logger().info(
        "application_started",
        environment=settings.environment,
        storage_backend=settings.storage_backend,
        queue_backend=settings.queue_backend,
    )
    yield
    await runtime.shutdown()
    structlog.get_logger().info("application_stopped")


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title="个人知识关系系统 API",
        version=__version__,
        docs_url="/docs" if settings.environment != "production" else None,
        redoc_url=None,
        lifespan=lifespan,
    )

    @application.middleware("http")
    async def request_context(request: Request, call_next):  # type: ignore[no-untyped-def]
        request_id = request.headers.get("X-Request-ID", str(uuid4()))
        context = TraceContext.root(request_id=request_id, actor_type="http")
        with context.activate():
            structlog.contextvars.bind_contextvars(
                request_id=request_id,
                trace_id=context.trace_id,
                span_id=context.span_id,
            )
            try:
                response = await call_next(request)
            finally:
                structlog.contextvars.clear_contextvars()
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Trace-ID"] = context.trace_id
        return response

    application.add_middleware(
        CORSMiddleware,
        allow_origins=[str(origin).rstrip("/") for origin in settings.cors_origins],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID", "X-Idempotency-Key"],
    )
    register_error_handlers(application)
    application.include_router(api_router, prefix="/v1")
    return application


app = create_app()
