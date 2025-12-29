"""FastAPI application factory and configuration."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from agent.cache.redis_client import close_redis, init_redis

from .config import get_api_settings
from .handlers import register_exception_handlers
from .middleware import LoggingMiddleware, RequestIDMiddleware
from .routers import (
    health_router,
    milestones_router,
    sessions_router,
    snapshots_router,
    tasks_router,
    websocket_router,
)

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager.

    Handles startup and shutdown events.

    Args:
        app: FastAPI application

    Yields:
        None
    """
    # Startup
    logger.info("starting_application")
    await init_redis()

    yield

    # Shutdown
    logger.info("shutting_down_application")
    await close_redis()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        Configured FastAPI application
    """
    settings = get_api_settings()

    app = FastAPI(
        title=settings.title,
        description=settings.description,
        version=settings.version,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
        openapi_tags=[
            {"name": "health", "description": "Health check endpoints"},
            {"name": "sessions", "description": "Session management"},
            {"name": "tasks", "description": "Task execution and management"},
            {"name": "milestones", "description": "Session milestone tracking"},
            {"name": "snapshots", "description": "Memory snapshot management"},
            {"name": "websocket", "description": "Real-time WebSocket connections"},
        ],
    )

    # Register middleware (order matters - first added = last executed)
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.add_middleware(LoggingMiddleware)
    app.add_middleware(RequestIDMiddleware)

    # CORS
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # Register exception handlers
    register_exception_handlers(app)

    # Register routers
    api_prefix = "/api/v1"

    # Health checks (no prefix)
    app.include_router(health_router)

    # API routes
    app.include_router(sessions_router, prefix=api_prefix)
    app.include_router(tasks_router, prefix=api_prefix)
    app.include_router(milestones_router, prefix=api_prefix)
    app.include_router(snapshots_router, prefix=api_prefix)

    # WebSocket (under api prefix)
    app.include_router(websocket_router, prefix=api_prefix)

    logger.info(
        "application_configured",
        title=settings.title,
        version=settings.version,
        debug=settings.debug,
    )

    return app


# Application instance
app = create_app()
