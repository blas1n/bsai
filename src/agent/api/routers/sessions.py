"""Session management endpoints."""

from uuid import UUID

from fastapi import APIRouter, status

from agent.db.models.enums import SessionStatus

from ..dependencies import Cache, CurrentUserId, DBSession
from ..schemas import (
    PaginatedResponse,
    SessionCreate,
    SessionDetailResponse,
    SessionResponse,
)
from ..services import SessionService

router = APIRouter(prefix="/sessions", tags=["sessions"])


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
