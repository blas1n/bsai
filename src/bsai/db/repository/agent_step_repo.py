"""Repository for agent step operations.

Provides pure data access methods for agent steps.
Business logic (status determination, duration calculation) is in AgentStepService.
"""

from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.agent_step import AgentStep
from .base import BaseRepository


class AgentStepRepository(BaseRepository[AgentStep]):
    """Repository for managing agent execution steps.

    Provides pure query methods for tracking individual agent executions
    within tasks and milestones.

    Note: Business logic methods (start_step, complete_step) have been moved
    to AgentStepService. Use the service for creating and completing steps.
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize repository.

        Args:
            session: Database session
        """
        super().__init__(AgentStep, session)

    async def get_steps_by_task(
        self,
        task_id: UUID,
        include_completed: bool = True,
    ) -> list[AgentStep]:
        """Get all agent steps for a task.

        Args:
            task_id: Task UUID
            include_completed: Whether to include completed steps

        Returns:
            List of AgentStep instances ordered by started_at
        """
        stmt = select(AgentStep).where(AgentStep.task_id == task_id)
        if not include_completed:
            stmt = stmt.where(AgentStep.status != "completed")
        stmt = stmt.order_by(AgentStep.started_at)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_steps_by_milestone(self, milestone_id: UUID) -> list[AgentStep]:
        """Get all agent steps for a milestone.

        Args:
            milestone_id: Milestone UUID

        Returns:
            List of AgentStep instances ordered by started_at
        """
        stmt = (
            select(AgentStep)
            .where(AgentStep.milestone_id == milestone_id)
            .order_by(AgentStep.started_at)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_cost_breakdown_by_agent(
        self,
        task_id: UUID,
    ) -> dict[str, dict[str, Any]]:
        """Get cost breakdown by agent type for a task.

        Args:
            task_id: Task UUID

        Returns:
            Dict mapping agent_type to cost/token summary
        """
        steps = await self.get_steps_by_task(task_id)

        breakdown: dict[str, dict[str, Any]] = {}
        for step in steps:
            if step.agent_type not in breakdown:
                breakdown[step.agent_type] = {
                    "total_cost_usd": Decimal("0"),
                    "total_input_tokens": 0,
                    "total_output_tokens": 0,
                    "step_count": 0,
                    "total_duration_ms": 0,
                }

            breakdown[step.agent_type]["total_cost_usd"] += step.cost_usd
            breakdown[step.agent_type]["total_input_tokens"] += step.input_tokens
            breakdown[step.agent_type]["total_output_tokens"] += step.output_tokens
            breakdown[step.agent_type]["step_count"] += 1
            if step.duration_ms:
                breakdown[step.agent_type]["total_duration_ms"] += step.duration_ms

        return breakdown
