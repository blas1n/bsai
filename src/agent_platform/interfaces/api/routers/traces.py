"""
Trace and observability endpoints
"""

from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
import structlog

from agent_platform.interfaces.api.dependencies.auth import get_current_user

logger = structlog.get_logger()
router = APIRouter()


class TraceResponse(BaseModel):
    """Trace response"""

    trace_id: UUID
    status: str
    duration_ms: int


@router.get("/{trace_id}", response_model=TraceResponse)
async def get_trace(
    trace_id: UUID,
    current_user: dict = Depends(get_current_user),
) -> TraceResponse:
    """Get trace by ID"""
    logger.info("fetching_trace", trace_id=str(trace_id))
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Trace retrieval not yet implemented",
    )
