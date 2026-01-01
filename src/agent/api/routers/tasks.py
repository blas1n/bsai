"""Task management endpoints."""

from uuid import UUID

from fastapi import APIRouter, status

from agent.db.models.enums import TaskStatus

from ..dependencies import Cache, CurrentUserId, DBSession, WSManager
from ..schemas import (
    PaginatedResponse,
    TaskCreate,
    TaskDetailResponse,
    TaskResponse,
)
from ..services import TaskService

router = APIRouter(prefix="/sessions/{session_id}/tasks", tags=["tasks"])


@router.post(
    "",
    response_model=TaskResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Create and execute task",
)
async def create_task(
    session_id: UUID,
    request: TaskCreate,
    db: DBSession,
    cache: Cache,
    ws_manager: WSManager,
    user_id: CurrentUserId,
) -> TaskResponse:
    """Create a new task and start execution.

    The task will be executed asynchronously. Use WebSocket
    to receive real-time progress updates.

    Args:
        session_id: Session UUID
        request: Task creation request
        db: Database session
        cache: Session cache
        ws_manager: WebSocket connection manager
        user_id: Current user ID

    Returns:
        Created task (202 Accepted)
    """
    service = TaskService(db, cache, ws_manager)
    return await service.create_and_execute_task(
        session_id=session_id,
        user_id=user_id,
        request=request,
    )


@router.get(
    "",
    response_model=PaginatedResponse[TaskResponse],
    summary="List session tasks",
)
async def list_tasks(
    session_id: UUID,
    db: DBSession,
    cache: Cache,
    ws_manager: WSManager,
    user_id: CurrentUserId,
    status: TaskStatus | None = None,
    limit: int = 20,
    offset: int = 0,
) -> PaginatedResponse[TaskResponse]:
    """List tasks for a session.

    Args:
        session_id: Session UUID
        db: Database session
        cache: Session cache
        ws_manager: WebSocket connection manager
        user_id: Current user ID
        status: Optional status filter
        limit: Maximum results per page
        offset: Offset for pagination

    Returns:
        Paginated list of tasks
    """
    service = TaskService(db, cache, ws_manager)
    return await service.list_tasks(
        session_id=session_id,
        user_id=user_id,
        status=status,
        limit=min(limit, 100),
        offset=offset,
    )


@router.get(
    "/{task_id}",
    response_model=TaskDetailResponse,
    summary="Get task details",
)
async def get_task(
    session_id: UUID,
    task_id: UUID,
    db: DBSession,
    cache: Cache,
    ws_manager: WSManager,
    user_id: CurrentUserId,
) -> TaskDetailResponse:
    """Get detailed task information including milestones.

    Args:
        session_id: Session UUID (for URL consistency)
        task_id: Task UUID
        db: Database session
        cache: Session cache
        ws_manager: WebSocket connection manager
        user_id: Current user ID

    Returns:
        Task details with milestones
    """
    # session_id is included in path for REST consistency
    # but task_id is globally unique
    _ = session_id
    service = TaskService(db, cache, ws_manager)
    return await service.get_task(task_id, user_id)


@router.put(
    "/{task_id}/cancel",
    response_model=TaskResponse,
    summary="Cancel running task",
)
async def cancel_task(
    session_id: UUID,
    task_id: UUID,
    db: DBSession,
    cache: Cache,
    ws_manager: WSManager,
    user_id: CurrentUserId,
) -> TaskResponse:
    """Cancel a running task.

    Only tasks with status IN_PROGRESS can be cancelled.

    Args:
        session_id: Session UUID (for URL consistency)
        task_id: Task UUID
        db: Database session
        cache: Session cache
        ws_manager: WebSocket connection manager
        user_id: Current user ID

    Returns:
        Updated task
    """
    _ = session_id
    service = TaskService(db, cache, ws_manager)
    return await service.cancel_task(task_id, user_id)
