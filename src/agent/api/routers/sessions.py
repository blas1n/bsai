"""Session management endpoints."""

from typing import Any
from uuid import UUID

import structlog
from fastapi import APIRouter, status
from pydantic import BaseModel

from agent.db.models.enums import SessionStatus

from ..dependencies import Cache, CurrentUserId, DBSession
from ..schemas import (
    BulkSessionAction,
    PaginatedResponse,
    SessionCreate,
    SessionDetailResponse,
    SessionResponse,
)
from ..services import SessionService

router = APIRouter(prefix="/sessions", tags=["sessions"])
logger = structlog.get_logger()


class BulkActionResult(BaseModel):
    """Response for bulk actions."""

    success: list[str]
    failed: list[dict[str, Any]]


@router.post(
    "",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new session",
)
async def create_session(
    request: SessionCreate,
    db: DBSession,
    cache: Cache,
    user_id: CurrentUserId,
) -> SessionResponse:
    """Create a new session for the authenticated user.

    Args:
        request: Session creation request
        db: Database session
        cache: Session cache
        user_id: Current user ID

    Returns:
        Created session
    """
    service = SessionService(db, cache)
    return await service.create_session(
        user_id=user_id,
        metadata=request.metadata,
    )


@router.get(
    "",
    response_model=PaginatedResponse[SessionResponse],
    summary="List user sessions",
)
async def list_sessions(
    db: DBSession,
    cache: Cache,
    user_id: CurrentUserId,
    status: SessionStatus | None = None,
    limit: int = 20,
    offset: int = 0,
) -> PaginatedResponse[SessionResponse]:
    """List sessions for the authenticated user.

    Args:
        db: Database session
        cache: Session cache
        user_id: Current user ID
        status: Optional status filter
        limit: Maximum results per page
        offset: Offset for pagination

    Returns:
        Paginated list of sessions
    """
    service = SessionService(db, cache)
    return await service.list_sessions(
        user_id=user_id,
        status=status,
        limit=min(limit, 100),
        offset=offset,
    )


@router.post(
    "/bulk",
    response_model=BulkActionResult,
    summary="Bulk session actions",
)
async def bulk_session_action(
    request: BulkSessionAction,
    db: DBSession,
    cache: Cache,
    user_id: CurrentUserId,
) -> BulkActionResult:
    """Perform bulk actions on multiple sessions.

    Supports pause, complete, and delete actions.

    Args:
        request: Bulk action request with session IDs and action
        db: Database session
        cache: Session cache
        user_id: Current user ID

    Returns:
        Result with success and failed session IDs
    """
    service = SessionService(db, cache)
    success: list[str] = []
    failed: list[dict[str, Any]] = []

    logger.info(
        "bulk_action_started", action=request.action, session_count=len(request.session_ids)
    )

    for session_id in request.session_ids:
        try:
            if request.action == "pause":
                await service.pause_session(session_id, user_id)
            elif request.action == "complete":
                await service.complete_session(session_id, user_id)
            elif request.action == "delete":
                await service.delete_session(session_id, user_id)
            success.append(str(session_id))
            logger.info("bulk_action_success", action=request.action, session_id=str(session_id))
        except Exception as e:
            failed.append({"session_id": str(session_id), "error": str(e)})
            logger.error(
                "bulk_action_failed",
                action=request.action,
                session_id=str(session_id),
                error=str(e),
            )

    logger.info("bulk_action_completed", success_count=len(success), failed_count=len(failed))
    return BulkActionResult(success=success, failed=failed)


@router.get(
    "/{session_id}",
    response_model=SessionDetailResponse,
    summary="Get session details",
)
async def get_session(
    session_id: UUID,
    db: DBSession,
    cache: Cache,
    user_id: CurrentUserId,
) -> SessionDetailResponse:
    """Get detailed session information including tasks.

    Args:
        session_id: Session UUID
        db: Database session
        cache: Session cache
        user_id: Current user ID

    Returns:
        Session details with tasks
    """
    service = SessionService(db, cache)
    return await service.get_session(session_id, user_id)


@router.put(
    "/{session_id}/pause",
    response_model=SessionResponse,
    summary="Pause session",
)
async def pause_session(
    session_id: UUID,
    db: DBSession,
    cache: Cache,
    user_id: CurrentUserId,
) -> SessionResponse:
    """Pause an active session.

    Creates a memory snapshot of the current context
    for later resumption.

    Args:
        session_id: Session UUID
        db: Database session
        cache: Session cache
        user_id: Current user ID

    Returns:
        Updated session
    """
    service = SessionService(db, cache)
    return await service.pause_session(session_id, user_id)


@router.put(
    "/{session_id}/resume",
    response_model=SessionResponse,
    summary="Resume session",
)
async def resume_session(
    session_id: UUID,
    db: DBSession,
    cache: Cache,
    user_id: CurrentUserId,
) -> SessionResponse:
    """Resume a paused session.

    Restores context from the latest memory snapshot.

    Args:
        session_id: Session UUID
        db: Database session
        cache: Session cache
        user_id: Current user ID

    Returns:
        Updated session
    """
    service = SessionService(db, cache)
    session, _context = await service.resume_session(session_id, user_id)
    return session


@router.put(
    "/{session_id}/complete",
    response_model=SessionResponse,
    summary="Complete session",
)
async def complete_session(
    session_id: UUID,
    db: DBSession,
    cache: Cache,
    user_id: CurrentUserId,
) -> SessionResponse:
    """Mark session as completed.

    Args:
        session_id: Session UUID
        db: Database session
        cache: Session cache
        user_id: Current user ID

    Returns:
        Updated session
    """
    service = SessionService(db, cache)
    return await service.complete_session(session_id, user_id)


@router.delete(
    "/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete session",
)
async def delete_session(
    session_id: UUID,
    db: DBSession,
    cache: Cache,
    user_id: CurrentUserId,
) -> None:
    """Delete a completed or failed session.

    Args:
        session_id: Session UUID
        db: Database session
        cache: Session cache
        user_id: Current user ID
    """
    service = SessionService(db, cache)
    await service.delete_session(session_id, user_id)
