"""Memory snapshot repository for memory management operations."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.memory_snapshot import MemorySnapshot
from .base import BaseRepository


class MemorySnapshotRepository(BaseRepository[MemorySnapshot]):
    """Repository for MemorySnapshot model operations."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize memory snapshot repository.

        Args:
            session: Database session
        """
        super().__init__(MemorySnapshot, session)

    async def get_latest_snapshot(self, session_id: UUID) -> MemorySnapshot | None:
        """Get the most recent snapshot for a session.

        Args:
            session_id: Session UUID

        Returns:
            Latest memory snapshot or None if not found
        """
        stmt = (
            select(MemorySnapshot)
            .where(MemorySnapshot.session_id == session_id)
            .order_by(MemorySnapshot.created_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_session(self, session_id: UUID, limit: int = 10) -> list[MemorySnapshot]:
        """Get snapshots for a session, most recent first.

        Args:
            session_id: Session UUID
            limit: Maximum number of snapshots to return

        Returns:
            List of memory snapshots
        """
        stmt = (
            select(MemorySnapshot)
            .where(MemorySnapshot.session_id == session_id)
            .order_by(MemorySnapshot.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_type(self, session_id: UUID, snapshot_type: str) -> list[MemorySnapshot]:
        """Get snapshots by type for a session.

        Args:
            session_id: Session UUID
            snapshot_type: Snapshot type (auto, manual, milestone)

        Returns:
            List of memory snapshots of the specified type
        """
        stmt = (
            select(MemorySnapshot)
            .where(
                MemorySnapshot.session_id == session_id,
                MemorySnapshot.snapshot_type == snapshot_type,
            )
            .order_by(MemorySnapshot.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
