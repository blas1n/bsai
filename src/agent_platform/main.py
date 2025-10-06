"""
BSAI - Platform-oriented AI Agent Orchestrator
Main FastAPI application entry point
"""

from contextlib import asynccontextmanager
from typing import AsyncIterator

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app

from agent_platform.core.config import settings
from agent_platform.infrastructure.database.postgres import database
from agent_platform.infrastructure.cache.redis import redis_client
from agent_platform.interfaces.api.routers import (
    agents,
    prompts,
    experiments,
    traces,
    admin,
    health,
)

# Structured logging setup
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan context manager"""
    # Startup
    logger.info("starting_application", environment=settings.ENVIRONMENT)

    # Initialize database connection
    await database.connect()
    logger.info("database_connected")

    # Initialize Redis connection
    await redis_client.connect()
    logger.info("redis_connected")

    # Initialize LLM providers registry
    from agent_platform.core.llm.registry import llm_registry

    await llm_registry.initialize()
    logger.info("llm_providers_initialized")

    yield

    # Shutdown
    logger.info("shutting_down_application")

    # Close connections
    await database.disconnect()
    logger.info("database_disconnected")

    await redis_client.disconnect()
    logger.info("redis_disconnected")


def create_application() -> FastAPI:
    """Factory function to create FastAPI application"""

    app = FastAPI(
        title="BSAI - AI Agent Platform",
        description="Platform-oriented AI Agent Orchestrator with LLMOps capabilities",
        version="0.1.0",
        docs_url="/api/docs" if settings.ENVIRONMENT != "production" else None,
        redoc_url="/api/redoc" if settings.ENVIRONMENT != "production" else None,
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Request ID middleware
    from agent_platform.interfaces.api.middleware.request_id import RequestIDMiddleware

    app.add_middleware(RequestIDMiddleware)

    # Tracing middleware
    from agent_platform.interfaces.api.middleware.tracing import TracingMiddleware

    app.add_middleware(TracingMiddleware)

    # Include routers
    app.include_router(health.router, prefix="/api/health", tags=["Health"])
    app.include_router(agents.router, prefix="/api/v1/agents", tags=["Agents"])
    app.include_router(prompts.router, prefix="/api/v1/prompts", tags=["Prompts"])
    app.include_router(
        experiments.router, prefix="/api/v1/experiments", tags=["Experiments"]
    )
    app.include_router(traces.router, prefix="/api/v1/traces", tags=["Traces"])
    app.include_router(admin.router, prefix="/api/v1/admin", tags=["Admin"])

    # Prometheus metrics endpoint
    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)

    logger.info("application_created", environment=settings.ENVIRONMENT)

    return app


# Create application instance
app = create_application()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "agent_platform.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.ENVIRONMENT == "development",
        log_config=None,  # Use structlog instead
    )
