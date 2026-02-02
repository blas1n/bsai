"""Task CRUD service.

Handles task creation, retrieval, and status management.
"""

from __future__ import annotations

import asyncio
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from agent.api.exceptions import AccessDeniedError, InvalidStateError, NotFoundError
from agent.api.schemas import (
    AgentStepResponse,
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
