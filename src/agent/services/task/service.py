"""Task CRUD service.

Handles task creation, retrieval, and status management.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from agent.api.exceptions import AccessDeniedError, InvalidStateError, NotFoundError
from agent.api.schemas import (
    AgentStepResponse,
    EpicProgress,
    FeatureProgress,
    MilestoneDetailResponse,
    MilestoneResponse,
    PaginatedResponse,
    TaskCreate,
    TaskDetailResponse,
    TaskResponse,
)
from agent.api.websocket.manager import ConnectionManager
from agent.cache import SessionCache
from agent.db.models import Task
from agent.db.models.enums import SessionStatus, TaskStatus
from agent.db.repository.agent_step_repo import AgentStepRepository
from agent.db.repository.milestone_repo import MilestoneRepository
from agent.db.repository.session_repo import SessionRepository
from agent.db.repository.task_repo import TaskRepository
from agent.events import EventBus
from agent.llm.schemas import BreakpointConfig, QAConfig, QAResult
from agent.services import BreakpointService

from .executor import TaskExecutor
from .notifier import TaskNotifier

logger = structlog.get_logger()


class TaskService:
    """Task CRUD operations and management.

    Handles task creation, retrieval, and status updates.
    Delegates execution to TaskExecutor and notifications to TaskNotifier.
    """

    def __init__(
        self,
        db_session: AsyncSession,
        cache: SessionCache,
        event_bus: EventBus,
        ws_manager: ConnectionManager,
        breakpoint_service: BreakpointService,
    ) -> None:
        """Initialize task service.

        Args:
            db_session: Database session
            cache: Session cache
            event_bus: EventBus for event-driven notifications
            ws_manager: WebSocket manager for streaming
            breakpoint_service: BreakpointService for HITL workflows
        """
        self.db = db_session
        self.cache = cache
        self.event_bus = event_bus
        self.ws_manager = ws_manager
        self.breakpoint_service = breakpoint_service

        # Repositories
        self.session_repo = SessionRepository(db_session)
        self.task_repo = TaskRepository(db_session)
        self.milestone_repo = MilestoneRepository(db_session)
        self.agent_step_repo = AgentStepRepository(db_session)

        # Composed services
        self.notifier = TaskNotifier(ws_manager)
        self.executor = TaskExecutor(
            cache=cache,
            event_bus=event_bus,
            notifier=self.notifier,
            breakpoint_service=breakpoint_service,
        )

    async def create_and_execute_task(
        self,
        session_id: UUID,
        user_id: str,
        request: TaskCreate,
    ) -> TaskResponse:
        """Create task and start execution.

        Args:
            session_id: Session ID
            user_id: User ID
            request: Task creation request

        Returns:
            Created task response (202 Accepted)

        Raises:
            NotFoundError: If session not found
            AccessDeniedError: If user doesn't own session
            InvalidStateError: If session not active
        """
        # Verify session ownership and status
        session = await self.session_repo.get_by_id(session_id)
        if session is None:
            raise NotFoundError("Session", session_id)
        if session.user_id != user_id:
            raise AccessDeniedError("Session", session_id)
        if session.status != SessionStatus.ACTIVE.value:
            raise InvalidStateError(
                resource="Session",
                current_state=session.status,
                action="create tasks in",
            )

        # Create task
        task = await self.task_repo.create(
            session_id=session_id,
            original_request=request.original_request,
            status=TaskStatus.PENDING.value,
        )
        await self.db.commit()

        logger.info(
            "task_created",
            task_id=str(task.id),
            session_id=str(session_id),
        )

        # Start execution in background
        asyncio.create_task(
            self.executor.execute(
                session_id=session_id,
                task_id=task.id,
                original_request=request.original_request,
                max_context_tokens=request.max_context_tokens,
                stream=request.stream and self.ws_manager is not None,
                breakpoint_enabled=request.breakpoint_enabled,
                breakpoint_nodes=request.breakpoint_nodes,
            )
        )

        return TaskResponse.model_validate(task)

    async def get_task(
        self,
        task_id: UUID,
        user_id: str,
    ) -> TaskDetailResponse:
        """Get task details with milestones and agent steps.

        Args:
            task_id: Task ID
            user_id: User ID

        Returns:
            Task detail response with milestones, agent steps, and cost breakdown
        """
        task = await self._get_task_for_user(task_id, user_id)

        # Get milestones
        milestones = await self.milestone_repo.get_by_task_id(task_id)
        milestone_responses = [MilestoneResponse.model_validate(m) for m in milestones]

        # Get agent steps
        agent_steps = await self.agent_step_repo.get_steps_by_task(task_id)
        agent_step_responses = [AgentStepResponse.model_validate(s) for s in agent_steps]

        # Get cost breakdown by agent
        cost_breakdown = await self.agent_step_repo.get_cost_breakdown_by_agent(task_id)
        cost_breakdown_serializable = {
            agent: {
                "total_cost_usd": str(data["total_cost_usd"]),
                "total_input_tokens": data["total_input_tokens"],
                "total_output_tokens": data["total_output_tokens"],
                "step_count": data["step_count"],
                "total_duration_ms": data["total_duration_ms"],
            }
            for agent, data in cost_breakdown.items()
        }

        # Calculate progress
        if milestones:
            completed = sum(1 for m in milestones if m.status == "passed")
            progress = completed / len(milestones)
        else:
            progress = 0.0

        # Calculate total duration
        total_duration_ms = sum(s.duration_ms or 0 for s in agent_steps)

        return TaskDetailResponse(
            **TaskResponse.model_validate(task).model_dump(),
            milestones=milestone_responses,
            agent_steps=agent_step_responses,
            progress=progress,
            total_duration_ms=total_duration_ms if total_duration_ms > 0 else None,
            cost_breakdown=cost_breakdown_serializable,
        )

    async def list_tasks(
        self,
        session_id: UUID,
        user_id: str,
        status: TaskStatus | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> PaginatedResponse[TaskResponse]:
        """List session tasks.

        Args:
            session_id: Session ID
            user_id: User ID
            status: Optional status filter
            limit: Maximum results
            offset: Offset for pagination

        Returns:
            Paginated task response
        """
        # Verify session ownership
        session = await self.session_repo.get_by_id(session_id)
        if session is None:
            raise NotFoundError("Session", session_id)
        if session.user_id != user_id:
            raise AccessDeniedError("Session", session_id)

        # Get tasks
        tasks = await self.task_repo.get_by_session_id(
            session_id,
            limit=limit + 1,
            offset=offset,
        )

        # Filter by status if provided
        if status:
            tasks = [t for t in tasks if t.status == status.value]

        # Check if there are more
        has_more = len(tasks) > limit
        if has_more:
            tasks = tasks[:limit]

        return PaginatedResponse(
            items=[TaskResponse.model_validate(t) for t in tasks],
            total=len(tasks),
            limit=limit,
            offset=offset,
            has_more=has_more,
        )

    async def cancel_task(
        self,
        task_id: UUID,
        user_id: str,
    ) -> TaskResponse:
        """Cancel running task.

        Args:
            task_id: Task ID
            user_id: User ID

        Returns:
            Updated task response
        """
        task = await self._get_task_for_user(task_id, user_id)

        if task.status != TaskStatus.IN_PROGRESS.value:
            raise InvalidStateError(
                resource="Task",
                current_state=task.status,
                action="cancelled",
            )

        # Update task status
        cancelled_task = await self.task_repo.update(
            task_id,
            status=TaskStatus.FAILED.value,
            final_result="Task cancelled by user",
        )
        if cancelled_task is None:
            raise NotFoundError("Task", task_id)
        await self.db.commit()

        # Invalidate progress cache
        await self.cache.invalidate_task_progress(task_id)

        # Cleanup breakpoint state
        self.breakpoint_service.cleanup_task(task_id)

        logger.info("task_cancelled", task_id=str(task_id))

        return TaskResponse.model_validate(cancelled_task)

    async def resume_task(
        self,
        task_id: UUID,
        user_id: str,
        user_input: str | None = None,
        rejected: bool = False,
    ) -> TaskResponse:
        """Resume a task paused at a breakpoint.

        Args:
            task_id: Task ID
            user_id: User ID
            user_input: Optional user input to pass to the workflow
            rejected: If True with user_input, re-run worker with feedback.
                     If True without user_input, cancel the task.

        Returns:
            Updated task response
        """
        task = await self._get_task_for_user(task_id, user_id)

        # Task must be in progress and paused at a breakpoint
        if task.status != TaskStatus.IN_PROGRESS.value:
            raise InvalidStateError(
                resource="Task",
                current_state=task.status,
                action="resumed",
            )

        # Resume execution in background
        asyncio.create_task(
            self.executor.resume(
                session_id=task.session_id,
                task_id=task_id,
                user_input=user_input,
                rejected=rejected,
            )
        )

        logger.info(
            "task_resume_requested",
            task_id=str(task_id),
            has_user_input=user_input is not None,
            rejected=rejected,
        )

        return TaskResponse.model_validate(task)

    async def reject_task(
        self,
        task_id: UUID,
        user_id: str,
        reason: str | None = None,
    ) -> TaskResponse:
        """Reject and cancel a task at a breakpoint.

        Args:
            task_id: Task ID
            user_id: User ID
            reason: Optional rejection reason

        Returns:
            Updated task response
        """
        task = await self._get_task_for_user(task_id, user_id)

        if task.status != TaskStatus.IN_PROGRESS.value:
            raise InvalidStateError(
                resource="Task",
                current_state=task.status,
                action="rejected",
            )

        # Update task status
        final_result = f"Task rejected by user: {reason}" if reason else "Task rejected by user"
        rejected_task = await self.task_repo.update(
            task_id,
            status=TaskStatus.FAILED.value,
            final_result=final_result,
        )
        if rejected_task is None:
            raise NotFoundError("Task", task_id)
        await self.db.commit()

        # Invalidate progress cache
        await self.cache.invalidate_task_progress(task_id)

        # Cleanup breakpoint state
        self.breakpoint_service.cleanup_task(task_id)

        # Notify via WebSocket
        await self.notifier.notify_failed(
            session_id=task.session_id,
            task_id=task_id,
            error=final_result,
        )

        logger.info(
            "task_rejected",
            task_id=str(task_id),
            reason=reason,
        )

        return TaskResponse.model_validate(rejected_task)

    async def get_milestone(
        self,
        milestone_id: UUID,
        user_id: str,
    ) -> MilestoneDetailResponse:
        """Get milestone details.

        Args:
            milestone_id: Milestone ID
            user_id: User ID

        Returns:
            Milestone detail response
        """
        milestone = await self.milestone_repo.get_by_id(milestone_id)
        if milestone is None:
            raise NotFoundError("Milestone", milestone_id)

        # Verify task ownership
        await self._get_task_for_user(milestone.task_id, user_id)

        return MilestoneDetailResponse.model_validate(milestone)

    async def list_milestones(
        self,
        task_id: UUID,
        user_id: str,
    ) -> list[MilestoneResponse]:
        """List task milestones.

        Args:
            task_id: Task ID
            user_id: User ID

        Returns:
            List of milestone responses
        """
        await self._get_task_for_user(task_id, user_id)

        milestones = await self.milestone_repo.get_by_task_id(task_id)
        return [MilestoneResponse.model_validate(m) for m in milestones]

    async def get_progress(
        self,
        task_id: UUID,
        user_id: str,
    ) -> dict[str, Any]:
        """Get current task execution progress.

        Returns progress information including:
        - Overall completion percentage
        - Task/Feature/Epic level progress
        - Current breakpoint reason (if paused)

        Args:
            task_id: Task ID
            user_id: User ID

        Returns:
            Progress dictionary compatible with ProgressResponse
        """
        await self._get_task_for_user(task_id, user_id)

        # Get milestones for the task
        milestones = await self.milestone_repo.get_by_task_id(task_id)

        # Calculate progress
        total_tasks = len(milestones)
        completed_tasks = sum(1 for m in milestones if m.status == "passed")
        pending_tasks = sum(1 for m in milestones if m.status == "pending")
        failed_tasks = sum(1 for m in milestones if m.status == "failed")
        in_progress_tasks = sum(1 for m in milestones if m.status == "in_progress")

        # Calculate overall percentage
        overall_percent = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0

        # Find current task (first in_progress milestone)
        current_task = None
        for m in milestones:
            if m.status == "in_progress":
                current_task = str(m.id)
                break

        # Get breakpoint state
        breakpoint_state = self.breakpoint_service.get_state(task_id)
        breakpoint_reason = None
        if breakpoint_state and breakpoint_state.get("paused"):
            breakpoint_reason = breakpoint_state.get("reason", "Paused at breakpoint")

        # For now, feature and epic progress are empty lists
        # These would be populated from project_plan data if available
        feature_progress: list[FeatureProgress] = []
        epic_progress: list[EpicProgress] = []

        return {
            "total_tasks": total_tasks,
            "completed_tasks": completed_tasks,
            "pending_tasks": pending_tasks + in_progress_tasks,
            "failed_tasks": failed_tasks,
            "overall_percent": overall_percent,
            "current_task": current_task,
            "breakpoint_reason": breakpoint_reason,
            "feature_progress": feature_progress,
            "epic_progress": epic_progress,
        }

    async def update_breakpoint_config(
        self,
        task_id: UUID,
        user_id: str,
        config: BreakpointConfig,
    ) -> None:
        """Update breakpoint configuration during execution.

        Allows changing breakpoint settings while task is running.

        Args:
            task_id: Task ID
            user_id: User ID
            config: New breakpoint configuration
        """
        await self._get_task_for_user(task_id, user_id)

        # Update the breakpoint service configuration
        self.breakpoint_service.update_config(config)

        logger.info(
            "breakpoint_config_updated",
            task_id=str(task_id),
            pause_level=config.pause_level,
            pause_on_plan_review=config.pause_on_plan_review,
            pause_on_failure=config.pause_on_failure,
        )

    async def get_qa_result(
        self,
        task_id: UUID,
        user_id: str,
    ) -> QAResult | None:
        """Get QA validation results for a task.

        Retrieves the most recent QA result from the task's milestones.
        Returns None if no QA validation has been performed.

        Args:
            task_id: Task ID
            user_id: User ID

        Returns:
            QAResult containing validation details, or None if not found
        """
        await self._get_task_for_user(task_id, user_id)

        # Get the most recent milestone with QA result
        milestones = await self.milestone_repo.get_by_task_id(task_id)

        # Find the latest milestone with a QA result
        latest_qa_milestone = None
        for milestone in reversed(milestones):
            if milestone.qa_result:
                latest_qa_milestone = milestone
                break

        if latest_qa_milestone is None or not latest_qa_milestone.qa_result:
            return None

        # Parse the stored QA result
        # The qa_result field stores the QA feedback as text
        # We construct a QAResult from the available data
        qa_text = latest_qa_milestone.qa_result

        # Determine decision based on milestone status
        if latest_qa_milestone.status == "passed":
            decision = "PASS"
        else:
            decision = "RETRY"

        # Parse issues and suggestions from the qa_text if available
        static_issues: list[str] = []
        static_suggestions: list[str] = []
        summary = qa_text

        # Try to extract structured data from qa_text
        if "ISSUES FOUND" in qa_text:
            # Extract issues section
            parts = qa_text.split("ISSUES FOUND")
            if len(parts) > 1:
                issues_section = parts[1]
                if "SUGGESTIONS" in issues_section:
                    issues_part, suggestions_part = issues_section.split("SUGGESTIONS", 1)
                else:
                    issues_part = issues_section
                    suggestions_part = ""

                # Parse issue lines
                for line in issues_part.split("\n"):
                    line = line.strip()
                    if line.startswith("- "):
                        static_issues.append(line[2:])

                # Parse suggestion lines
                for line in suggestions_part.split("\n"):
                    line = line.strip()
                    if line.startswith("- "):
                        static_suggestions.append(line[2:])

        # Build QAResult
        # For now, we don't have persisted dynamic validation results
        # so those fields will be None
        qa_result = QAResult(
            decision=decision,  # type: ignore
            confidence=0.8 if decision == "PASS" else 0.6,
            static_issues=static_issues,
            static_suggestions=static_suggestions,
            summary=summary,
            lint_result=None,
            typecheck_result=None,
            test_result=None,
            build_result=None,
        )

        logger.debug(
            "qa_result_retrieved",
            task_id=str(task_id),
            milestone_id=str(latest_qa_milestone.id),
            decision=decision,
        )

        return qa_result

    async def update_qa_config(
        self,
        task_id: UUID,
        user_id: str,
        config: QAConfig,
    ) -> None:
        """Update QA configuration for a task.

        Updates the QA validation settings that will be used
        for subsequent milestone validations.

        Args:
            task_id: Task ID
            user_id: User ID
            config: New QA configuration
        """
        await self._get_task_for_user(task_id, user_id)

        # Store QA config in cache for the task
        cache_key = f"task:{task_id}:qa_config"
        await self.cache.client.setex(
            cache_key,
            3600,  # 1 hour TTL
            config.model_dump_json(),
        )

        logger.info(
            "qa_config_updated",
            task_id=str(task_id),
            validations=config.validations,
            allow_lint_warnings=config.allow_lint_warnings,
            require_all_tests_pass=config.require_all_tests_pass,
        )

    async def _get_task_for_user(
        self,
        task_id: UUID,
        user_id: str,
    ) -> Task:
        """Get task and verify ownership.

        Args:
            task_id: Task ID
            user_id: User ID

        Returns:
            Task model

        Raises:
            NotFoundError: If task not found
            AccessDeniedError: If user doesn't own task's session
        """
        task = await self.task_repo.get_by_id(task_id)
        if task is None:
            raise NotFoundError("Task", task_id)

        # Verify session ownership
        session = await self.session_repo.get_by_id(task.session_id)
        if session is None or session.user_id != user_id:
            raise AccessDeniedError("Task", task_id)

        return task

    # Delegation methods for backwards compatibility with existing tests
    async def _execute_task(
        self,
        session_id: UUID,
        task_id: UUID,
        original_request: str,
        max_context_tokens: int,
        stream: bool = False,
        breakpoint_enabled: bool = False,
        breakpoint_nodes: list[str] | None = None,
    ) -> None:
        """Execute task (delegates to TaskExecutor)."""
        await self.executor.execute(
            session_id=session_id,
            task_id=task_id,
            original_request=original_request,
            max_context_tokens=max_context_tokens,
            stream=stream,
            breakpoint_enabled=breakpoint_enabled,
            breakpoint_nodes=breakpoint_nodes,
        )

    async def _resume_task_execution(
        self,
        session_id: UUID,
        task_id: UUID,
        user_input: str | None = None,
        rejected: bool = False,
    ) -> None:
        """Resume task (delegates to TaskExecutor)."""
        await self.executor.resume(
            session_id=session_id,
            task_id=task_id,
            user_input=user_input,
            rejected=rejected,
        )

    async def _save_context_to_cache(
        self,
        session_id: UUID,
        final_state,
    ) -> None:
        """Save context to cache (delegates to TaskExecutor)."""
        await self.executor._save_context_to_cache(session_id, final_state)

    async def _handle_task_failure(
        self,
        db_session,
        session_id: UUID,
        task_id: UUID,
        final_state,
        total_input_tokens: int,
        total_output_tokens: int,
        total_cost,
        stream: bool,
    ) -> None:
        """Handle task failure (delegates to TaskExecutor)."""
        await self.executor._handle_failure(
            db_session=db_session,
            session_id=session_id,
            task_id=task_id,
            final_state=final_state,
            total_input_tokens=total_input_tokens,
            total_output_tokens=total_output_tokens,
            total_cost=total_cost,
            stream=stream,
        )
