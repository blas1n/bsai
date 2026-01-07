"""FastAPI application factory and configuration."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi_keycloak_middleware import setup_keycloak_middleware

from agent.cache import SessionCache
from agent.cache.redis_client import close_redis, get_redis, init_redis
from agent.db import close_db, init_db

from .auth import get_keycloak_config, user_mapper
from .config import get_api_settings, get_auth_settings, get_database_settings
from .handlers import register_exception_handlers
from .middleware import LoggingMiddleware, RequestIDMiddleware
from .routers import (
    artifacts_router,
    health_router,
    mcp_router,
    milestones_router,
    sessions_router,
    snapshots_router,
    tasks_router,
    websocket_router,
)
from .websocket import ConnectionManager

load_dotenv()
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
    db_settings = get_database_settings()
    init_db(db_settings.database_url)
    logger.info("database_initialized")
    await init_redis()
    logger.info("redis_initialized")

    # Initialize WebSocket manager
    cache = SessionCache(get_redis())
    app.state.ws_manager = ConnectionManager(cache=cache)
    logger.info("websocket_manager_initialized")

    yield

    # Shutdown
    logger.info("shutting_down_application")
    await close_redis()
    await close_db()
    logger.info("shutdown_complete")


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
            {"name": "mcp", "description": "MCP server configuration and tool logs"},
            {"name": "websocket", "description": "Real-time WebSocket connections"},
        ],
    )

    # Register middleware (order matters - last added = first to process request)
    # Per docs: "Add Keycloak middleware first, then CORS middleware, so CORS processes requests initially"

    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.add_middleware(LoggingMiddleware)
    app.add_middleware(RequestIDMiddleware)

    # Keycloak authentication middleware - added FIRST so it runs AFTER CORS
    auth_settings = get_auth_settings()
    if auth_settings.auth_enabled:
        setup_keycloak_middleware(
            app,
            keycloak_configuration=get_keycloak_config(),
            user_mapper=user_mapper,
            exclude_patterns=[
                "/docs",
                "/redoc",
                "/openapi.json",
                "/health",
                "/ready",
                # WebSocket handles its own authentication via token query param
                "/api/v1/ws",
                "/api/v1/ws/*",
            ],
        )

    # CORS middleware - added AFTER Keycloak so it runs FIRST (handles OPTIONS preflight)
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
    app.include_router(artifacts_router, prefix=api_prefix)
    app.include_router(mcp_router, prefix=api_prefix)

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
