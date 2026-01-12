"""Task execution service."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from agent.cache import SessionCache
from agent.db.models import Task
from agent.db.models.enums import SessionStatus, TaskStatus
from agent.db.repository.agent_step_repo import AgentStepRepository
from agent.db.repository.milestone_repo import MilestoneRepository
from agent.db.repository.session_repo import SessionRepository
from agent.db.repository.task_repo import TaskRepository
from agent.db.session import get_db_session
from agent.graph.state import AgentState
from agent.graph.workflow import WorkflowResult, WorkflowRunner

from ..exceptions import AccessDeniedError, InvalidStateError, NotFoundError
from ..schemas import (
    AgentStepResponse,
    MilestoneDetailResponse,
    MilestoneResponse,
    PaginatedResponse,
    PreviousMilestoneInfo,
    TaskCompletedPayload,
    TaskCreate,
    TaskDetailResponse,
    TaskFailedPayload,
    TaskResponse,
    TaskStartedPayload,
    WSMessage,
    WSMessageType,
)
from ..websocket.manager import ConnectionManager

logger = structlog.get_logger()


class TaskService:
    """Task execution and management.

    Handles task creation, execution with streaming, and status updates.
    """

    def __init__(
        self,
        db_session: AsyncSession,
        cache: SessionCache,
        ws_manager: ConnectionManager | None = None,
    ) -> None:
        """Initialize task service.

        Args:
            db_session: Database session
            cache: Session cache
            ws_manager: Optional WebSocket manager for streaming
        """
        self.db = db_session
        self.cache = cache
        self.ws_manager = ws_manager
        self.session_repo = SessionRepository(db_session)
        self.task_repo = TaskRepository(db_session)
        self.milestone_repo = MilestoneRepository(db_session)
        self.agent_step_repo = AgentStepRepository(db_session)

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
            self._execute_task(
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
        # Convert Decimal to string for JSON serialization
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
            self._resume_task_execution(
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

        # Notify via WebSocket
        if self.ws_manager:
            await self.ws_manager.broadcast_to_session(
                task.session_id,
                WSMessage(
                    type=WSMessageType.TASK_FAILED,
                    payload=TaskFailedPayload(
                        task_id=task_id,
                        error=final_result,
                    ).model_dump(),
                ),
            )

        logger.info(
            "task_rejected",
            task_id=str(task_id),
            reason=reason,
        )

        return TaskResponse.model_validate(rejected_task)

    async def _resume_task_execution(
        self,
        session_id: UUID,
        task_id: UUID,
        user_input: str | None = None,
        rejected: bool = False,
    ) -> None:
        """Resume task execution from breakpoint.

        Args:
            session_id: Session ID
            task_id: Task ID
            user_input: Optional user input to pass to workflow
            rejected: If True, pass rejected flag to workflow
        """
        try:
            # Clear the paused state before resuming (only if not rejected with feedback)
            # If rejected with feedback, we want to re-run worker, so keep paused state
            # If rejected without feedback, task will be cancelled anyway
            if self.ws_manager and not (rejected and user_input):
                self.ws_manager.clear_paused_at(task_id)
                logger.info(
                    "breakpoint_paused_state_cleared",
                    task_id=str(task_id),
                )

            async for db_session in get_db_session():
                runner = WorkflowRunner(
                    db_session,
                    ws_manager=self.ws_manager,
                    cache=self.cache,
                )

                # Prepare resume input with rejected flag if needed
                resume_data = None
                if user_input is not None or rejected:
                    resume_data = {
                        "user_input": user_input,
                        "rejected": rejected,
                    }
                    if rejected and not user_input:
                        # Rejected without feedback - this will cancel the task
                        resume_data["reason"] = "Task cancelled by user"

                # Resume workflow from checkpoint
                result: WorkflowResult = await runner.resume(
                    task_id=task_id,
                    user_input=resume_data,
                )

                if result is None:
                    logger.error(
                        "task_resume_failed_no_state",
                        task_id=str(task_id),
                    )
                    return

                final_state = result.state

                # Check if workflow was interrupted again (another breakpoint)
                if result.interrupted:
                    logger.info(
                        "task_paused_at_breakpoint_after_resume",
                        task_id=str(task_id),
                        interrupt_node=result.interrupt_node,
                    )
                    # Task remains IN_PROGRESS, waiting for resume
                    return

                # Handle completion (similar to _execute_task)
                task_status = final_state.get("task_status")
                if task_status == TaskStatus.FAILED:
                    await self._handle_task_failure(
                        db_session=db_session,
                        session_id=session_id,
                        task_id=task_id,
                        final_state=final_state,
                        total_input_tokens=final_state.get("total_input_tokens", 0),
                        total_output_tokens=final_state.get("total_output_tokens", 0),
                        total_cost=Decimal(final_state.get("total_cost_usd", "0")),
                        stream=True,
                    )
                    return

                # Task completed successfully
                final_result = final_state.get("final_response", "")
                if not final_result:
                    milestones = final_state.get("milestones", [])
                    if milestones:
                        last_milestone = milestones[-1]
                        final_result = last_milestone.get("worker_output", "")

                # Update task status
                task_repo = TaskRepository(db_session)
                await task_repo.update(
                    task_id,
                    status=TaskStatus.COMPLETED.value,
                    final_result=final_result,
                )
                await db_session.commit()

                # Notify completion
                if self.ws_manager:
                    total_tokens = final_state.get("total_input_tokens", 0) + final_state.get(
                        "total_output_tokens", 0
                    )
                    await self.ws_manager.broadcast_to_session(
                        session_id,
                        WSMessage(
                            type=WSMessageType.TASK_COMPLETED,
                            payload=TaskCompletedPayload(
                                task_id=task_id,
                                final_result=final_result or "Task completed",
                                total_tokens=total_tokens,
                                total_cost_usd=Decimal(final_state.get("total_cost_usd", "0")),
                                duration_seconds=0,  # Not tracked for resumed tasks
                            ).model_dump(),
                        ),
                    )

        except Exception as e:
            logger.exception(
                "task_resume_execution_failed",
                task_id=str(task_id),
                error=str(e),
            )

            # Notify failure
            if self.ws_manager:
                async for db_session in get_db_session():
                    task_repo = TaskRepository(db_session)
                    task = await task_repo.get_by_id(task_id)
                    if task:
                        await self.ws_manager.broadcast_to_session(
                            task.session_id,
                            WSMessage(
                                type=WSMessageType.TASK_FAILED,
                                payload=TaskFailedPayload(
                                    task_id=task_id,
                                    error=str(e),
                                ).model_dump(),
                            ),
                        )
                    break

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
        """Execute task with optional WebSocket streaming.

        Args:
            session_id: Session ID
            task_id: Task ID
            original_request: User's request
            max_context_tokens: Max context size
            stream: Whether to stream updates via WebSocket
            breakpoint_enabled: Whether breakpoints are enabled
            breakpoint_nodes: List of node names to pause at
        """
        start_time = datetime.now(UTC)

        try:
            # Update task status to IN_PROGRESS at the start of execution
            async for db_session in get_db_session():
                task_repo = TaskRepository(db_session)
                await task_repo.update(task_id, status=TaskStatus.IN_PROGRESS.value)
                await db_session.commit()
                break

            # Notify task started (streaming only)
            if stream and self.ws_manager:
                # Get previous milestones for session continuity
                previous_milestones: list[PreviousMilestoneInfo] = []
                async for db_session in get_db_session():
                    milestone_repo = MilestoneRepository(db_session)
                    db_milestones = await milestone_repo.get_by_session_id(session_id)
                    previous_milestones = [
                        PreviousMilestoneInfo(
                            id=m.id,
                            sequence_number=m.sequence_number,
                            description=m.description,
                            complexity=m.complexity,
                            status=m.status,
                            worker_output=m.worker_output[:500] if m.worker_output else None,
                        )
                        for m in db_milestones
                    ]
                    break  # Only need one iteration

                await self.ws_manager.broadcast_to_session(
                    session_id,
                    WSMessage(
                        type=WSMessageType.TASK_STARTED,
                        payload=TaskStartedPayload(
                            task_id=task_id,
                            session_id=session_id,
                            original_request=original_request,
                            milestone_count=0,
                            previous_milestones=previous_milestones,
                        ).model_dump(),
                    ),
                )

            async for db_session in get_db_session():
                # Pass ws_manager only when streaming
                runner = WorkflowRunner(
                    db_session,
                    ws_manager=self.ws_manager if stream else None,
                    cache=self.cache,
                )

                # Execute workflow
                result: WorkflowResult = await runner.run(
                    session_id=session_id,
                    task_id=task_id,
                    original_request=original_request,
                    max_context_tokens=max_context_tokens,
                    breakpoint_enabled=breakpoint_enabled,
                    breakpoint_nodes=breakpoint_nodes,
                )

                final_state = result.state

                # Check if workflow was interrupted (paused at breakpoint)
                if result.interrupted:
                    logger.info(
                        "task_paused_at_breakpoint",
                        task_id=str(task_id),
                        interrupt_node=result.interrupt_node,
                    )
                    # Task remains IN_PROGRESS, waiting for resume
                    # Don't update status or notify completion
                    return

                # Calculate duration
                duration = (datetime.now(UTC) - start_time).total_seconds()

                # Get actual token counts and cost from state
                total_input_tokens = final_state.get("total_input_tokens", 0)
                total_output_tokens = final_state.get("total_output_tokens", 0)
                total_tokens = total_input_tokens + total_output_tokens
                total_cost = Decimal(final_state.get("total_cost_usd", "0"))

                # Check if task failed (e.g., max retries exceeded)
                task_status = final_state.get("task_status")
                task_failed = task_status == TaskStatus.FAILED

                if task_failed:
                    await self._handle_task_failure(
                        db_session=db_session,
                        session_id=session_id,
                        task_id=task_id,
                        final_state=final_state,
                        total_input_tokens=total_input_tokens,
                        total_output_tokens=total_output_tokens,
                        total_cost=total_cost,
                        stream=stream,
                    )
                    return

                # Get final result from Responder agent
                # Falls back to last milestone output if responder didn't run
                final_result = final_state.get("final_response", "")
                if not final_result:
                    # Fallback to last milestone's worker output
                    milestones = final_state.get("milestones", [])
                    if milestones:
                        last_milestone = milestones[-1]
                        final_result = last_milestone.get("worker_output", "")

                logger.info(
                    "task_completed_tokens",
                    task_id=str(task_id),
                    input_tokens=total_input_tokens,
                    output_tokens=total_output_tokens,
                    total_cost=str(total_cost),
                )

                # Update task status
                task_repo = TaskRepository(db_session)
                await task_repo.update(
                    task_id,
                    status=TaskStatus.COMPLETED.value,
                    final_result=final_result,
                )

                # Update session totals
                session_repo = SessionRepository(db_session)
                session = await session_repo.get_by_id(session_id)
                if session:
                    new_input_tokens = session.total_input_tokens + total_input_tokens
                    new_output_tokens = session.total_output_tokens + total_output_tokens
                    new_cost = session.total_cost_usd + total_cost
                    await session_repo.update(
                        session_id,
                        total_input_tokens=new_input_tokens,
                        total_output_tokens=new_output_tokens,
                        total_cost_usd=new_cost,
                    )
                    logger.info(
                        "session_totals_updated",
                        session_id=str(session_id),
                        new_input_tokens=new_input_tokens,
                        new_output_tokens=new_output_tokens,
                        new_cost=str(new_cost),
                    )

                await db_session.commit()

                # Cache context for next task in session
                await self._save_context_to_cache(
                    session_id=session_id,
                    final_state=final_state,
                )

                # Notify completion after commit (streaming only)
                if stream and self.ws_manager:
                    await self.ws_manager.broadcast_to_session(
                        session_id,
                        WSMessage(
                            type=WSMessageType.TASK_COMPLETED,
                            payload=TaskCompletedPayload(
                                task_id=task_id,
                                final_result=final_result or "Task completed",
                                total_tokens=total_tokens,
                                total_cost_usd=total_cost,
                                duration_seconds=duration,
                            ).model_dump(),
                        ),
                    )

        except Exception as e:
            logger.exception(
                "task_execution_failed",
                task_id=str(task_id),
                error=str(e),
            )

            # Notify failure (streaming only)
            if stream and self.ws_manager:
                await self.ws_manager.broadcast_to_session(
                    session_id,
                    WSMessage(
                        type=WSMessageType.TASK_FAILED,
                        payload=TaskFailedPayload(
                            task_id=task_id,
                            error=str(e),
                            failed_milestone=None,
                        ).model_dump(),
                    ),
                )

            # Update task status
            async for db_session in get_db_session():
                task_repo = TaskRepository(db_session)
                await task_repo.update(
                    task_id,
                    status=TaskStatus.FAILED.value,
                    final_result=str(e),
                )
                await db_session.commit()

    async def _handle_task_failure(
        self,
        db_session: AsyncSession,
        session_id: UUID,
        task_id: UUID,
        final_state: AgentState,
        total_input_tokens: int,
        total_output_tokens: int,
        total_cost: Decimal,
        stream: bool,
    ) -> None:
        """Handle task failure: update DB and notify via WebSocket.

        Args:
            db_session: Database session
            session_id: Session ID
            task_id: Task ID
            final_state: Final workflow state
            total_input_tokens: Total input tokens used
            total_output_tokens: Total output tokens used
            total_cost: Total cost in USD
            stream: Whether to send WebSocket notifications
        """
        error_message = final_state.get("error", "Task failed after maximum retry attempts")

        logger.warning(
            "task_failed",
            task_id=str(task_id),
            error=error_message,
        )

        # Update task status
        task_repo = TaskRepository(db_session)
        await task_repo.update(
            task_id,
            status=TaskStatus.FAILED.value,
            final_result=error_message,
        )

        # Update session totals even on failure
        session_repo = SessionRepository(db_session)
        session = await session_repo.get_by_id(session_id)
        if session:
            new_input_tokens = session.total_input_tokens + total_input_tokens
            new_output_tokens = session.total_output_tokens + total_output_tokens
            new_cost = session.total_cost_usd + total_cost
            await session_repo.update(
                session_id,
                total_input_tokens=new_input_tokens,
                total_output_tokens=new_output_tokens,
                total_cost_usd=new_cost,
            )

        await db_session.commit()

        # Notify failure (streaming only)
        if stream and self.ws_manager:
            current_idx = final_state.get("current_milestone_index", 0)
            await self.ws_manager.broadcast_to_session(
                session_id,
                WSMessage(
                    type=WSMessageType.TASK_FAILED,
                    payload=TaskFailedPayload(
                        task_id=task_id,
                        error=error_message or "Unknown error",
                        failed_milestone=current_idx + 1,
                    ).model_dump(),
                ),
            )

    async def _save_context_to_cache(
        self,
        session_id: UUID,
        final_state: AgentState,
    ) -> None:
        """Save conversation context to cache for session continuity.

        Args:
            session_id: Session ID
            final_state: Final workflow state containing context messages
        """
        context_messages = final_state.get("context_messages", [])
        context_summary = final_state.get("context_summary")

        if not context_messages:
            return

        token_count = final_state.get("current_context_tokens")
        if token_count is None:
            logger.warning(
                "context_not_cached_missing_token_count",
                session_id=str(session_id),
            )
            return

        # Convert ChatMessage objects to dicts for JSON serialization
        messages_data = [{"role": msg.role, "content": msg.content} for msg in context_messages]

        # Use longer TTL for session context (2 hours)
        await self.cache.cache_context(
            session_id=session_id,
            context=messages_data,
            token_count=token_count,
            summary=context_summary,
            ttl=7200,  # 2 hours
        )

        logger.info(
            "context_saved_to_cache",
            session_id=str(session_id),
            message_count=len(messages_data),
            has_summary=context_summary is not None,
            token_count=token_count,
        )
