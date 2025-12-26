"""Milestone repository for milestone-specific operations."""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.milestone import Milestone
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
            List of milestones ordered by sequence_order
        """
        stmt = (
            select(Milestone)
            .where(Milestone.task_id == task_id)
            .order_by(Milestone.sequence_order.asc())
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
            .order_by(Milestone.sequence_order.asc())
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
            .order_by(Milestone.sequence_order.asc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def assign_llm(
        self, milestone_id: UUID, llm_model: str
    ) -> Milestone | None:
        """Assign LLM model to milestone.

        Args:
            milestone_id: Milestone UUID
            llm_model: LLM model name

        Returns:
            Updated milestone or None if not found
        """
        return await self.update(milestone_id, assigned_llm=llm_model)

    async def record_worker_result(
        self,
        milestone_id: UUID,
        worker_result: str,
        tokens_used: int,
        cost: Decimal,
    ) -> Milestone | None:
        """Record Worker agent output and usage.

        Args:
            milestone_id: Milestone UUID
            worker_result: Worker agent output
            tokens_used: Tokens consumed
            cost: Cost in USD

        Returns:
            Updated milestone or None if not found
        """
        return await self.update(
            milestone_id,
            worker_result=worker_result,
            tokens_used=tokens_used,
            cost=cost,
            status="qa_pending",
        )

    async def record_qa_result(
        self,
        milestone_id: UUID,
        qa_passed: bool,
        qa_feedback: str | None = None,
    ) -> Milestone | None:
        """Record QA agent validation result.

        Args:
            milestone_id: Milestone UUID
            qa_passed: Whether QA validation passed
            qa_feedback: Optional QA feedback

        Returns:
            Updated milestone or None if not found
        """
        milestone = await self.get_by_id(milestone_id)
        if milestone is None:
            return None

        milestone.qa_passed = qa_passed
        milestone.qa_feedback = qa_feedback
        milestone.qa_attempts += 1

        if qa_passed:
            milestone.status = "completed"
        elif milestone.qa_attempts >= 3:
            milestone.status = "failed"
        else:
            milestone.status = "retry"

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
            .order_by(Milestone.sequence_order.asc())
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
