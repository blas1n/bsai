"""Repository for agent step operations."""

import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.agent_step import AgentStep
from .base import BaseRepository


class AgentStepRepository(BaseRepository[AgentStep]):
    """Repository for managing agent execution steps.

    Provides methods for tracking individual agent executions
    within tasks and milestones.
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize repository.

        Args:
            session: Database session
        """
        super().__init__(AgentStep, session)

    async def start_step(
        self,
        task_id: UUID,
        agent_type: str,
        milestone_id: UUID | None = None,
        input_summary: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AgentStep:
        """Record start of an agent execution step.

        Args:
            task_id: Task UUID
            agent_type: Type of agent (conductor, worker, qa, etc.)
            milestone_id: Optional milestone UUID
            input_summary: Brief summary of input
            metadata: Additional metadata

        Returns:
            Created AgentStep instance
        """
        return await self.create(
            task_id=task_id,
            milestone_id=milestone_id,
            agent_type=agent_type,
            status="started",
            input_summary=input_summary,
            metadata_json=json.dumps(metadata) if metadata else None,
        )

    async def complete_step(
        self,
        step_id: UUID,
        output_summary: str | None = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost_usd: Decimal = Decimal("0"),
        error_message: str | None = None,
    ) -> AgentStep | None:
        """Record completion of an agent execution step.

        Args:
            step_id: AgentStep UUID
            output_summary: Brief summary of output
            input_tokens: Tokens consumed for input
            output_tokens: Tokens generated
            cost_usd: Cost in USD
            error_message: Error message if failed

        Returns:
            Updated AgentStep instance or None if not found
        """
        step = await self.get_by_id(step_id)
        if step is None:
            return None

        now = datetime.now(UTC)
        duration_ms = int((now - step.started_at).total_seconds() * 1000)

        step.status = "failed" if error_message else "completed"
        step.ended_at = now
        step.duration_ms = duration_ms
        step.output_summary = output_summary
        step.input_tokens = input_tokens
        step.output_tokens = output_tokens
        step.cost_usd = cost_usd
        step.error_message = error_message

        await self.session.flush()
        await self.session.refresh(step)
        return step

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
