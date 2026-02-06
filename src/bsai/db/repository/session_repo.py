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

    async def get_by_user_id(self, user_id: str, limit: int = 10, offset: int = 0) -> list[Session]:
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

    async def get_active_sessions(self, user_id: str | None = None) -> list[Session]:
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

    async def update_tokens(
        self, session_id: UUID, input_tokens: int, output_tokens: int
    ) -> Session | None:
        """Increment session token usage.

        Args:
            session_id: Session UUID
            input_tokens: Number of input tokens to add
            output_tokens: Number of output tokens to add

        Returns:
            Updated session or None if not found
        """
        session_obj = await self.get_by_id(session_id)
        if session_obj is None:
            return None

        session_obj.total_input_tokens += input_tokens
        session_obj.total_output_tokens += output_tokens

        await self.session.flush()
        await self.session.refresh(session_obj)
        return session_obj

    async def update_cost(self, session_id: UUID, cost_increment: Decimal) -> Session | None:
        """Increment session cost.

        Args:
            session_id: Session UUID
            cost_increment: Cost to add (in USD)

        Returns:
            Updated session or None if not found
        """
        session_obj = await self.get_by_id(session_id)
        if session_obj is None:
            return None

        session_obj.total_cost_usd += cost_increment

        await self.session.flush()
        await self.session.refresh(session_obj)
        return session_obj

    async def get_total_cost_by_user(self, user_id: str) -> Decimal:
        """Calculate total cost across all user sessions.

        Args:
            user_id: External user identifier

        Returns:
            Total cost in USD
        """
        stmt = select(func.sum(Session.total_cost_usd)).where(Session.user_id == user_id)
        result = await self.session.execute(stmt)
        total = result.scalar_one_or_none()
        return total if total is not None else Decimal("0.0")

    async def verify_ownership(self, session_id: UUID, user_id: str) -> bool:
        """Verify that a user owns a session.

        Args:
            session_id: Session UUID to verify
            user_id: User ID to check ownership

        Returns:
            True if user owns the session, False otherwise
        """
        stmt = select(Session.id).where(
            Session.id == session_id,
            Session.user_id == user_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None
