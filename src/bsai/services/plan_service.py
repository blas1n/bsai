"""Plan Service for managing project plans.

Handles the Human-in-the-Loop workflow:
- Plan review and approval
- Plan revision based on user feedback
- Plan status management
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from bsai.db.repository.project_plan_repo import ProjectPlanRepository
from bsai.llm.schemas import PlanStatus

if TYPE_CHECKING:
    from bsai.core.architect import ArchitectAgent
    from bsai.db.models.project_plan import ProjectPlan

logger = structlog.get_logger()


class PlanNotFoundError(Exception):
    """Raised when plan is not found."""

    pass


class InvalidPlanStateError(Exception):
    """Raised when plan state transition is invalid."""

    pass


class PlanService:
    """Service for managing project plans.

    Handles the Human-in-the-Loop workflow including:
    - Retrieving plans
    - Approving plans for execution
    - Requesting revisions based on user feedback
    - Rejecting plans
    - Managing execution state and progress
    """

    def __init__(
        self,
        session: AsyncSession,
        architect: ArchitectAgent | None = None,
    ) -> None:
        """Initialize Plan Service.

        Args:
            session: Database session
            architect: Optional Architect agent for revisions
        """
        self.session = session
        self.repo = ProjectPlanRepository(session)
        self.architect = architect

    async def get_plan(self, plan_id: UUID) -> ProjectPlan:
        """Get plan by ID.

        Args:
            plan_id: Plan UUID

        Returns:
            ProjectPlan instance

        Raises:
            PlanNotFoundError: If plan not found
        """
        plan = await self.repo.get_by_id(plan_id)
        if not plan:
            raise PlanNotFoundError(f"Plan not found: {plan_id}")
        return plan

    async def get_plan_by_task(self, task_id: UUID) -> ProjectPlan | None:
        """Get plan by task ID.

        Args:
            task_id: Task UUID

        Returns:
            ProjectPlan or None if not found
        """
        return await self.repo.get_by_task_id(task_id)

    async def approve_plan(
        self,
        plan_id: UUID,
        approved_by: str | None = None,
    ) -> ProjectPlan:
        """Approve a plan for execution.

        Transitions plan from DRAFT to APPROVED status.

        Args:
            plan_id: Plan UUID to approve
            approved_by: Optional identifier of approver

        Returns:
            Updated ProjectPlan instance

        Raises:
            PlanNotFoundError: If plan not found
            InvalidPlanStateError: If plan is not in DRAFT status
        """
        plan = await self.get_plan(plan_id)

        if plan.status != PlanStatus.DRAFT.value:
            raise InvalidPlanStateError(
                f"Cannot approve plan in {plan.status} status. Must be DRAFT."
            )

        plan.status = PlanStatus.APPROVED.value
        plan.approved_at = datetime.utcnow()
        plan.approved_by = approved_by
        plan.updated_at = datetime.utcnow()

        await self.session.commit()
        await self.session.refresh(plan)

        logger.info("plan_approved", plan_id=str(plan_id), approved_by=approved_by)
        return plan

    async def request_revision(
        self,
        plan_id: UUID,
        feedback: str,
    ) -> ProjectPlan:
        """Request plan revision with user feedback.

        Uses the Architect agent to revise the plan based on
        user feedback while maintaining the plan in DRAFT status.

        Args:
            plan_id: Plan UUID to revise
            feedback: User's revision feedback

        Returns:
            Updated ProjectPlan instance with revised plan data

        Raises:
            PlanNotFoundError: If plan not found
            InvalidPlanStateError: If plan is not in DRAFT status
            RuntimeError: If Architect agent not configured
        """
        plan = await self.get_plan(plan_id)

        if plan.status != PlanStatus.DRAFT.value:
            raise InvalidPlanStateError(
                f"Cannot revise plan in {plan.status} status. Must be DRAFT."
            )

        if not self.architect:
            raise RuntimeError("Architect agent not configured for revision")

        logger.info(
            "plan_revision_requested",
            plan_id=str(plan_id),
            feedback_length=len(feedback),
        )

        # Delegate to Architect for intelligent revision
        revised_plan = await self.architect.revise_plan(
            plan_id=plan_id,
            user_feedback=feedback,
        )

        # Update plan with revised data
        plan.plan_data = revised_plan.plan_data
        plan.title = revised_plan.title
        plan.overview = revised_plan.overview
        plan.tech_stack = revised_plan.tech_stack
        plan.structure_type = revised_plan.structure_type
        plan.total_tasks = revised_plan.total_tasks
        plan.updated_at = datetime.utcnow()

        await self.session.commit()
        await self.session.refresh(plan)

        logger.info(
            "plan_revised",
            plan_id=str(plan_id),
            new_total_tasks=plan.total_tasks,
        )
        return plan

    async def reject_plan(
        self,
        plan_id: UUID,
        reason: str | None = None,
    ) -> ProjectPlan:
        """Reject a plan.

        Transitions plan from DRAFT to REJECTED status.

        Args:
            plan_id: Plan UUID to reject
            reason: Optional rejection reason

        Returns:
            Updated ProjectPlan instance

        Raises:
            PlanNotFoundError: If plan not found
            InvalidPlanStateError: If plan is not in DRAFT status
        """
        plan = await self.get_plan(plan_id)

        if plan.status != PlanStatus.DRAFT.value:
            raise InvalidPlanStateError(
                f"Cannot reject plan in {plan.status} status. Must be DRAFT."
            )

        plan.status = PlanStatus.REJECTED.value
        plan.updated_at = datetime.utcnow()

        await self.session.commit()
        await self.session.refresh(plan)

        logger.info("plan_rejected", plan_id=str(plan_id), reason=reason)
        return plan

    async def start_execution(self, plan_id: UUID) -> ProjectPlan:
        """Mark plan as in progress.

        Transitions plan from APPROVED to IN_PROGRESS status.

        Args:
            plan_id: Plan UUID

        Returns:
            Updated ProjectPlan instance

        Raises:
            PlanNotFoundError: If plan not found
            InvalidPlanStateError: If plan is not in APPROVED status
        """
        plan = await self.get_plan(plan_id)

        if plan.status != PlanStatus.APPROVED.value:
            raise InvalidPlanStateError(
                f"Cannot start plan in {plan.status} status. Must be APPROVED."
            )

        plan.status = PlanStatus.IN_PROGRESS.value
        plan.updated_at = datetime.utcnow()

        await self.session.commit()
        await self.session.refresh(plan)

        logger.info("plan_execution_started", plan_id=str(plan_id))
        return plan

    async def complete_plan(self, plan_id: UUID) -> ProjectPlan:
        """Mark plan as completed.

        Transitions plan to COMPLETED status.

        Args:
            plan_id: Plan UUID

        Returns:
            Updated ProjectPlan instance

        Raises:
            PlanNotFoundError: If plan not found
        """
        plan = await self.get_plan(plan_id)

        plan.status = PlanStatus.COMPLETED.value
        plan.updated_at = datetime.utcnow()

        await self.session.commit()
        await self.session.refresh(plan)

        logger.info(
            "plan_completed",
            plan_id=str(plan_id),
            total_tasks=plan.total_tasks,
            completed_tasks=plan.completed_tasks,
        )
        return plan

    async def update_progress(
        self,
        plan_id: UUID,
        completed_tasks: int,
        failed_tasks: int = 0,
    ) -> ProjectPlan:
        """Update plan progress statistics.

        Args:
            plan_id: Plan UUID
            completed_tasks: Number of completed tasks
            failed_tasks: Number of failed tasks (default: 0)

        Returns:
            Updated ProjectPlan instance

        Raises:
            PlanNotFoundError: If plan not found
        """
        plan = await self.get_plan(plan_id)

        plan.completed_tasks = completed_tasks
        plan.failed_tasks = failed_tasks
        plan.updated_at = datetime.utcnow()

        await self.session.commit()
        await self.session.refresh(plan)

        logger.debug(
            "plan_progress_updated",
            plan_id=str(plan_id),
            completed_tasks=completed_tasks,
            failed_tasks=failed_tasks,
            total_tasks=plan.total_tasks,
        )
        return plan
