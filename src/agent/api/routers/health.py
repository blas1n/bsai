"""Health check endpoints."""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    version: str = "0.1.0"


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Check API health status.

    Returns:
        Health status response
    """
    return HealthResponse(status="healthy")


@router.get("/ready", response_model=HealthResponse)
async def readiness_check() -> HealthResponse:
    """Check API readiness.

    Returns:
        Readiness status response
    """
    # TODO: Add database and Redis connectivity checks
    return HealthResponse(status="ready")
