"""
Health check endpoints
"""

from typing import Dict
from fastapi import APIRouter, status
from pydantic import BaseModel
import structlog

logger = structlog.get_logger()

router = APIRouter()


class HealthResponse(BaseModel):
    """Health check response"""

    status: str
    version: str
    environment: str


class DetailedHealthResponse(BaseModel):
    """Detailed health check response"""

    status: str
    version: str
    environment: str
    components: Dict[str, str]


@router.get("/", response_model=HealthResponse, status_code=status.HTTP_200_OK)
async def health_check() -> HealthResponse:
    """Basic health check endpoint"""
    from agent_platform.core.config import settings

    return HealthResponse(
        status="healthy", version="0.1.0", environment=settings.ENVIRONMENT
    )


@router.get(
    "/detailed", response_model=DetailedHealthResponse, status_code=status.HTTP_200_OK
)
async def detailed_health_check() -> DetailedHealthResponse:
    """Detailed health check with component status"""
    from agent_platform.core.config import settings
    from agent_platform.infrastructure.database.postgres import database
    from agent_platform.infrastructure.cache.redis import redis_client

    components = {}

    # Check database
    try:
        await database.execute("SELECT 1")
        components["database"] = "healthy"
    except Exception as e:
        logger.error("database_health_check_failed", error=str(e))
        components["database"] = "unhealthy"

    # Check Redis
    try:
        await redis_client.ping()
        components["redis"] = "healthy"
    except Exception as e:
        logger.error("redis_health_check_failed", error=str(e))
        components["redis"] = "unhealthy"

    overall_status = "healthy" if all(
        v == "healthy" for v in components.values()
    ) else "degraded"

    return DetailedHealthResponse(
        status=overall_status,
        version="0.1.0",
        environment=settings.ENVIRONMENT,
        components=components,
    )


@router.get("/ready", status_code=status.HTTP_200_OK)
async def readiness_check() -> Dict[str, str]:
    """Kubernetes readiness probe"""
    return {"status": "ready"}


@router.get("/live", status_code=status.HTTP_200_OK)
async def liveness_check() -> Dict[str, str]:
    """Kubernetes liveness probe"""
    return {"status": "alive"}
