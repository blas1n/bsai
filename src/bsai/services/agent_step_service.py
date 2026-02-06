"""Agent step service for managing agent execution steps.

Handles business logic for tracking agent steps, including:
- Starting steps with proper status initialization
- Completing steps with duration calculation and status determination
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from bsai.db.models.agent_step import AgentStep
from bsai.db.repository.agent_step_repo import AgentStepRepository

logger = structlog.get_logger()


class AgentStepService:
    """Service for managing agent execution steps.

    Handles business logic for agent step lifecycle:
    - Starting steps (status initialization)
    - Completing steps (duration calculation, status determination)

    Repository is used only for pure data access.
    """

    # Status constants
    STATUS_STARTED = "started"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"

    def __init__(self, db_session: AsyncSession) -> None:
        """Initialize agent step service.

        Args:
            db_session: Database session
        """
        self.db = db_session
        self.repo = AgentStepRepository(db_session)

    async def start_step(
        self,
        task_id: UUID,
        agent_type: str,
        milestone_id: UUID | None = None,
        input_summary: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AgentStep:
        """Record start of an agent execution step.

        Business logic:
        - Sets initial status to 'started'
        - Serializes metadata to JSON

        Args:
            task_id: Task UUID
            agent_type: Type of agent (conductor, worker, qa, etc.)
            milestone_id: Optional milestone UUID
            input_summary: Brief summary of input
            metadata: Additional metadata

        Returns:
            Created AgentStep instance
        """
        step = await self.repo.create(
            task_id=task_id,
            milestone_id=milestone_id,
            agent_type=agent_type,
            status=self.STATUS_STARTED,
            input_summary=input_summary,
            metadata_json=json.dumps(metadata) if metadata else None,
        )

        logger.info(
            "agent_step_started",
            step_id=str(step.id),
            task_id=str(task_id),
            agent_type=agent_type,
            milestone_id=str(milestone_id) if milestone_id else None,
        )

        return step

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

        Business logic:
        - Calculates duration from started_at to now
        - Determines status based on error presence (failed/completed)
        - Sets ended_at timestamp

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
        step = await self.repo.get_by_id(step_id)
        if step is None:
            logger.warning("agent_step_not_found", step_id=str(step_id))
            return None

        # Business logic: calculate duration
        now = datetime.now(UTC)
        duration_ms = int((now - step.started_at).total_seconds() * 1000)

        # Business logic: determine status based on error
        status = self.STATUS_FAILED if error_message else self.STATUS_COMPLETED

        # Update via repository
        updated_step = await self.repo.update(
            step_id,
            status=status,
            ended_at=now,
            duration_ms=duration_ms,
            output_summary=output_summary,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            error_message=error_message,
        )

        if updated_step:
            logger.info(
                "agent_step_completed",
                step_id=str(step_id),
                status=status,
                duration_ms=duration_ms,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=str(cost_usd),
            )

        return updated_step

    async def get_steps_by_task(
        self,
        task_id: UUID,
        include_completed: bool = True,
    ) -> list[AgentStep]:
        """Get all agent steps for a task.

        Delegates to repository for pure query.

        Args:
            task_id: Task UUID
            include_completed: Whether to include completed steps

        Returns:
            List of AgentStep instances ordered by started_at
        """
        return await self.repo.get_steps_by_task(task_id, include_completed)

    async def get_steps_by_milestone(self, milestone_id: UUID) -> list[AgentStep]:
        """Get all agent steps for a milestone.

        Delegates to repository for pure query.

        Args:
            milestone_id: Milestone UUID

        Returns:
            List of AgentStep instances ordered by started_at
        """
        return await self.repo.get_steps_by_milestone(milestone_id)

    async def get_cost_breakdown_by_agent(
        self,
        task_id: UUID,
    ) -> dict[str, dict[str, Any]]:
        """Get cost breakdown by agent type for a task.

        Delegates to repository for aggregation query.

        Args:
            task_id: Task UUID

        Returns:
            Dict mapping agent_type to cost/token summary
        """
        return await self.repo.get_cost_breakdown_by_agent(task_id)
