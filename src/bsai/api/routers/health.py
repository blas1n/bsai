"""Health check endpoints for Kubernetes probes.

- /health (liveness): Is the app process alive?
- /ready (readiness): Can the app handle traffic?
"""

import logging

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text

from bsai.cache.redis_client import get_redis
from bsai.db.session import get_session_manager

from ..exceptions import ServiceUnavailableError

router = APIRouter(tags=["health"])
logger = logging.getLogger(__name__)


class LivenessResponse(BaseModel):
    """Liveness check response."""

    status: str
    version: str = "0.1.0"


class ReadinessResponse(BaseModel):
    """Readiness check response."""

    status: str
    database: str
    redis: str


async def check_database() -> str:
    """Check database connectivity.

    Returns:
        'healthy' if connected, 'unhealthy' otherwise
    """
    try:
        manager = get_session_manager()
        async for session in manager.get_session():
            await session.execute(text("SELECT 1"))
            return "healthy"
    except Exception as e:
        logger.warning("database_health_check_failed: %s", str(e))
        return "unhealthy"
    return "unhealthy"


async def check_redis() -> str:
    """Check Redis connectivity.

    Returns:
        'healthy' if connected, 'unhealthy' otherwise
    """
    try:
        redis_client = get_redis()
        if redis_client.is_connected:
            await redis_client.client.ping()
            return "healthy"
        return "unhealthy"
    except Exception as e:
        logger.warning("redis_health_check_failed: %s", str(e))
        return "unhealthy"


@router.get("/health", response_model=LivenessResponse)
async def health_check() -> LivenessResponse:
    """Liveness probe - checks if the app is alive.

    Used by Kubernetes to determine if the container should be restarted.
    Does NOT check external dependencies (DB, Redis) to avoid cascading failures.

    Returns:
        Simple alive status
    """
    return LivenessResponse(status="healthy")


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    responses={503: {"model": ReadinessResponse}},
)
async def readiness_check() -> ReadinessResponse:
    """Readiness probe - checks if the app can handle traffic.

    Used by Kubernetes to determine if traffic should be routed to this pod.
    Checks all external dependencies (DB, Redis).

    Returns:
        200: Ready to handle traffic
        503: Not ready (dependencies unavailable)
    """
    db_status = await check_database()
    redis_status = await check_redis()

    unhealthy_services: list[str] = []
    if db_status != "healthy":
        unhealthy_services.append("database")
    if redis_status != "healthy":
        unhealthy_services.append("redis")

    if unhealthy_services:
        raise ServiceUnavailableError(
            service=", ".join(unhealthy_services),
            detail=f"database={db_status}, redis={redis_status}",
        )

    return ReadinessResponse(
        status="ready",
        database=db_status,
        redis=redis_status,
    )
