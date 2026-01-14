"""Milestone endpoints."""

from uuid import UUID

from fastapi import APIRouter

from ..dependencies import (
    AppBreakpointService,
    AppEventBus,
    Cache,
    CurrentUserId,
    DBSession,
    WSManager,
)
from ..schemas import MilestoneDetailResponse, MilestoneResponse
from ..services import TaskService

router = APIRouter(prefix="/tasks/{task_id}/milestones", tags=["milestones"])


@router.get(
    "",
    response_model=list[MilestoneResponse],
    summary="List task milestones",
)
async def list_milestones(
    task_id: UUID,
    db: DBSession,
    cache: Cache,
    event_bus: AppEventBus,
    ws_manager: WSManager,
    breakpoint_service: AppBreakpointService,
    user_id: CurrentUserId,
) -> list[MilestoneResponse]:
    """List all milestones for a task.

    Args:
        task_id: Task UUID
        db: Database session
        cache: Session cache
        event_bus: EventBus for event-driven notifications
        ws_manager: WebSocket connection manager
        breakpoint_service: BreakpointService for HITL workflows
        user_id: Current user ID

    Returns:
        List of milestones
    """
    service = TaskService(db, cache, event_bus, ws_manager, breakpoint_service)
    return await service.list_milestones(task_id, user_id)


@router.get(
    "/{milestone_id}",
    response_model=MilestoneDetailResponse,
    summary="Get milestone details",
)
async def get_milestone(
    task_id: UUID,
    milestone_id: UUID,
    db: DBSession,
    cache: Cache,
    event_bus: AppEventBus,
    ws_manager: WSManager,
    breakpoint_service: AppBreakpointService,
    user_id: CurrentUserId,
) -> MilestoneDetailResponse:
    """Get detailed milestone information.

    Args:
        task_id: Task UUID (for URL consistency)
        milestone_id: Milestone UUID
        db: Database session
        cache: Session cache
        event_bus: EventBus for event-driven notifications
        ws_manager: WebSocket connection manager
        breakpoint_service: BreakpointService for HITL workflows
        user_id: Current user ID

    Returns:
        Milestone details
    """
    # task_id is included in path for REST consistency
    _ = task_id
    service = TaskService(db, cache, event_bus, ws_manager, breakpoint_service)
    return await service.get_milestone(milestone_id, user_id)
