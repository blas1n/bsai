"""Session repository for session-specific operations."""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.session import Session
from .base import BaseRepository


class SessionRepository(BaseRepository[Session]):
    """Repository for Session model operations."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize session repository.

        Args:
            session: Database session
        """
        super().__init__(Session, session)

    async def get_by_user_id(
        self, user_id: str, limit: int = 10, offset: int = 0
    ) -> list[Session]:
        """Get sessions by user ID.

        Args:
            user_id: External user identifier
            limit: Maximum number of sessions to return
            offset: Number of sessions to skip

        Returns:
            List of sessions for the user
        """
        stmt = (
            select(Session)
            .where(Session.user_id == user_id)
            .order_by(Session.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_active_sessions(
        self, user_id: str | None = None
    ) -> list[Session]:
        """Get all active sessions, optionally filtered by user.

        Args:
            user_id: Optional user ID filter

        Returns:
            List of active sessions
        """
        stmt = select(Session).where(Session.status == "active")

        if user_id is not None:
            stmt = stmt.where(Session.user_id == user_id)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_cost(
        self, session_id: UUID, tokens_used: int, cost: Decimal
    ) -> Session | None:
        """Increment session cost and token usage.

        Args:
            session_id: Session UUID
            tokens_used: Number of tokens to add
            cost: Cost to add (in USD)

        Returns:
            Updated session or None if not found
        """
        session = await self.get_by_id(session_id)
        if session is None:
            return None

        session.total_tokens_used += tokens_used
        session.total_cost += cost

        await self.session.flush()
        await self.session.refresh(session)
        return session

    async def get_total_cost_by_user(self, user_id: str) -> Decimal:
        """Calculate total cost across all user sessions.

        Args:
            user_id: External user identifier

        Returns:
            Total cost in USD
        """
        stmt = select(func.sum(Session.total_cost)).where(
            Session.user_id == user_id
        )
        result = await self.session.execute(stmt)
        total = result.scalar_one_or_none()
        return total if total is not None else Decimal("0.0")

    async def close_session(self, session_id: UUID) -> Session | None:
        """Mark session as completed.

        Args:
            session_id: Session UUID

        Returns:
            Updated session or None if not found
        """
        return await self.update(session_id, status="completed")

    async def pause_session(self, session_id: UUID) -> Session | None:
        """Mark session as paused.

        Args:
            session_id: Session UUID

        Returns:
            Updated session or None if not found
        """
        return await self.update(session_id, status="paused")
