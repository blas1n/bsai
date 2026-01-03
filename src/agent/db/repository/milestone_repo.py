"""Milestone repository for milestone-specific operations."""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.milestone import Milestone
from ..models.task import Task
from .base import BaseRepository


class MilestoneRepository(BaseRepository[Milestone]):
    """Repository for Milestone model operations."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize milestone repository.

        Args:
            session: Database session
        """
        super().__init__(Milestone, session)

    async def get_by_task_id(self, task_id: UUID) -> list[Milestone]:
        """Get milestones by task ID, ordered by sequence.

        Args:
            task_id: Task UUID

        Returns:
            List of milestones ordered by sequence_number
        """
        stmt = (
            select(Milestone)
            .where(Milestone.task_id == task_id)
            .order_by(Milestone.sequence_number.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_pending_milestones(self, task_id: UUID) -> list[Milestone]:
        """Get pending milestones for a task.

        Args:
            task_id: Task UUID

        Returns:
            List of pending milestones ordered by sequence
        """
        stmt = (
            select(Milestone)
            .where(Milestone.task_id == task_id, Milestone.status == "pending")
            .order_by(Milestone.sequence_number.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_next_milestone(self, task_id: UUID) -> Milestone | None:
        """Get the next pending milestone for a task.

        Args:
            task_id: Task UUID

        Returns:
            Next pending milestone or None if all complete
        """
        stmt = (
            select(Milestone)
            .where(Milestone.task_id == task_id, Milestone.status == "pending")
            .order_by(Milestone.sequence_number.asc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def increment_retry_count(self, milestone_id: UUID) -> int:
        """Increment and return the retry count for a milestone.

        Args:
            milestone_id: Milestone UUID

        Returns:
            Updated retry count
        """
        milestone = await self.get_by_id(milestone_id)
        if milestone is None:
            return 0

        milestone.retry_count += 1
        await self.session.flush()
        await self.session.refresh(milestone)
        return milestone.retry_count

    async def update_llm_usage(
        self,
        milestone_id: UUID,
        input_tokens: int,
        output_tokens: int,
        cost: Decimal,
    ) -> Milestone | None:
        """Update milestone LLM usage statistics.

        Args:
            milestone_id: Milestone UUID
            input_tokens: Input tokens consumed
            output_tokens: Output tokens consumed
            cost: Cost in USD

        Returns:
            Updated milestone or None if not found
        """
        milestone = await self.get_by_id(milestone_id)
        if milestone is None:
            return None

        milestone.input_tokens += input_tokens
        milestone.output_tokens += output_tokens
        milestone.cost_usd += cost

        await self.session.flush()
        await self.session.refresh(milestone)
        return milestone

    async def get_failed_milestones(self, task_id: UUID) -> list[Milestone]:
        """Get all failed milestones for a task.

        Args:
            task_id: Task UUID

        Returns:
            List of failed milestones
        """
        stmt = (
            select(Milestone)
            .where(Milestone.task_id == task_id, Milestone.status == "failed")
            .order_by(Milestone.sequence_number.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_milestones_by_complexity(
        self, complexity: str, limit: int = 100
    ) -> list[Milestone]:
        """Get milestones by complexity level for analysis.

        Args:
            complexity: Complexity level (trivial, simple, moderate, complex, context_heavy)
            limit: Maximum number of milestones to return

        Returns:
            List of milestones with specified complexity
        """
        stmt = (
            select(Milestone)
            .where(Milestone.complexity == complexity)
            .order_by(Milestone.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_session_id(self, session_id: UUID) -> list[Milestone]:
        """Get all milestones for a session (across all tasks).

        Args:
            session_id: Session UUID

        Returns:
            List of milestones ordered by task creation time and sequence number
        """
        stmt = (
            select(Milestone)
            .join(Task, Milestone.task_id == Task.id)
            .where(Task.session_id == session_id)
            .order_by(Task.created_at.asc(), Milestone.sequence_number.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_max_sequence_for_session(self, session_id: UUID) -> int:
        """Get the maximum sequence number across all milestones in a session.

        Args:
            session_id: Session UUID

        Returns:
            Maximum sequence number or 0 if no milestones exist
        """
        stmt = (
            select(func.max(Milestone.sequence_number))
            .join(Task, Milestone.task_id == Task.id)
            .where(Task.session_id == session_id)
        )
        result = await self.session.execute(stmt)
        max_seq = result.scalar_one_or_none()
        return max_seq or 0
