"""LLM usage log repository for usage tracking operations."""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.llm_usage_log import LLMUsageLog
from .base import BaseRepository


class LLMUsageLogRepository(BaseRepository[LLMUsageLog]):
    """Repository for LLMUsageLog model operations."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize LLM usage log repository.

        Args:
            session: Database session
        """
        super().__init__(LLMUsageLog, session)

    async def get_by_session(self, session_id: UUID, limit: int = 100) -> list[LLMUsageLog]:
        """Get all LLM usage logs for a session.

        Args:
            session_id: Session UUID
            limit: Maximum number of logs to return

        Returns:
            List of LLM usage logs
        """
        stmt = (
            select(LLMUsageLog)
            .where(LLMUsageLog.session_id == session_id)
            .order_by(LLMUsageLog.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_total_cost(self, session_id: UUID) -> Decimal:
        """Calculate total cost for a session.

        Args:
            session_id: Session UUID

        Returns:
            Total cost in USD
        """
        stmt = select(func.sum(LLMUsageLog.cost)).where(LLMUsageLog.session_id == session_id)
        result = await self.session.execute(stmt)
        total = result.scalar_one_or_none()
        return total if total is not None else Decimal("0.0")

    async def get_by_agent_type(self, agent_type: str, limit: int = 100) -> list[LLMUsageLog]:
        """Get LLM usage logs by agent type for analysis.

        Args:
            agent_type: Agent type (architect, worker, qa, responder)
            limit: Maximum number of logs to return

        Returns:
            List of LLM usage logs
        """
        stmt = (
            select(LLMUsageLog)
            .where(LLMUsageLog.agent_type == agent_type)
            .order_by(LLMUsageLog.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_milestone(self, milestone_id: UUID) -> list[LLMUsageLog]:
        """Get all LLM usage logs for a milestone.

        Args:
            milestone_id: Milestone UUID

        Returns:
            List of LLM usage logs
        """
        stmt = (
            select(LLMUsageLog)
            .where(LLMUsageLog.milestone_id == milestone_id)
            .order_by(LLMUsageLog.created_at.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
