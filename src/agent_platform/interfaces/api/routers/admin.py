"""
Admin endpoints for platform management
"""

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
import structlog

from agent_platform.interfaces.api.dependencies.auth import get_current_user, require_admin

logger = structlog.get_logger()
router = APIRouter()


class CostSummaryResponse(BaseModel):
    """Cost summary response"""

    total_cost_usd: float
    total_tokens: int
    period: str


@router.get(
    "/cost/summary",
    response_model=CostSummaryResponse,
    dependencies=[Depends(require_admin)],
)
async def get_cost_summary(
    period: str = "today",
) -> CostSummaryResponse:
    """Get cost summary for specified period"""
    logger.info("fetching_cost_summary", period=period)
    # Placeholder
    return CostSummaryResponse(total_cost_usd=0.0, total_tokens=0, period=period)
