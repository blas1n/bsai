"""Memory snapshot endpoints."""

from uuid import UUID

from fastapi import APIRouter, status

from ..dependencies import Cache, CurrentUserId, DBSession
from ..schemas import SnapshotCreate, SnapshotResponse
from ..services import SessionService

router = APIRouter(prefix="/sessions/{session_id}/snapshots", tags=["snapshots"])


@router.get(
    "",
    response_model=list[SnapshotResponse],
    summary="List session snapshots",
)
async def list_snapshots(
    session_id: UUID,
    db: DBSession,
    cache: Cache,
    user_id: CurrentUserId,
) -> list[SnapshotResponse]:
    """List all memory snapshots for a session.

    Args:
        session_id: Session UUID
        db: Database session
        cache: Session cache
        user_id: Current user ID

    Returns:
        List of snapshots
    """
    service = SessionService(db, cache)
    return await service.list_snapshots(session_id, user_id)


@router.post(
    "",
    response_model=SnapshotResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create manual snapshot",
)
async def create_snapshot(
    session_id: UUID,
    request: SnapshotCreate,
    db: DBSession,
    cache: Cache,
    user_id: CurrentUserId,
) -> SnapshotResponse:
    """Create a manual memory snapshot.

    This preserves the current session context for later resumption.

    Args:
        session_id: Session UUID
        request: Snapshot creation request
        db: Database session
        cache: Session cache
        user_id: Current user ID

    Returns:
        Created snapshot
    """
    service = SessionService(db, cache)
    return await service.create_snapshot(session_id, user_id, request.reason)


@router.get(
    "/latest",
    response_model=SnapshotResponse,
    summary="Get latest snapshot",
)
async def get_latest_snapshot(
    session_id: UUID,
    db: DBSession,
    cache: Cache,
    user_id: CurrentUserId,
) -> SnapshotResponse:
    """Get the most recent memory snapshot.

    Args:
        session_id: Session UUID
        db: Database session
        cache: Session cache
        user_id: Current user ID

    Returns:
        Latest snapshot
    """
    service = SessionService(db, cache)
    return await service.get_latest_snapshot(session_id, user_id)


@router.get(
    "/{snapshot_id}",
    response_model=SnapshotResponse,
    summary="Get snapshot details",
)
async def get_snapshot(
    session_id: UUID,
    snapshot_id: UUID,
    db: DBSession,
    cache: Cache,
    user_id: CurrentUserId,
) -> SnapshotResponse:
    """Get snapshot details.

    Args:
        session_id: Session UUID (for URL consistency)
        snapshot_id: Snapshot UUID
        db: Database session
        cache: Session cache
        user_id: Current user ID

    Returns:
        Snapshot details
    """
    _ = session_id
    service = SessionService(db, cache)
    return await service.get_snapshot(snapshot_id, user_id)
