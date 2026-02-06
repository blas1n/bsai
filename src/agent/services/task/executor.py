"""Task execution service.

Handles workflow execution and resumption logic.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from agent.cache import SessionCache

if TYPE_CHECKING:
    from agent.api.schemas import PreviousMilestoneInfo
from agent.db.models.enums import TaskStatus
from agent.db.repository.milestone_repo import MilestoneRepository
from agent.db.repository.session_repo import SessionRepository
from agent.db.repository.task_repo import TaskRepository
from agent.db.session import get_db_session
from agent.events import EventBus
from agent.graph.state import AgentState
from agent.graph.workflow import WorkflowResult, WorkflowRunner
from agent.services import BreakpointService

from .notifier import TaskNotifier

logger = structlog.get_logger()


class TaskExecutor:
    """Handles task workflow execution.

    Responsible for running and resuming task workflows.
    """

    def __init__(
        self,
        cache: SessionCache,
        event_bus: EventBus,
        notifier: TaskNotifier,
        breakpoint_service: BreakpointService,
    ) -> None:
        """Initialize task executor.

        Args:
            cache: Session cache for context persistence
            event_bus: EventBus for event-driven notifications
            notifier: TaskNotifier for WebSocket broadcasts
            breakpoint_service: Service for HITL workflows
        """
        self.cache = cache
        self.event_bus = event_bus
        self.notifier = notifier
        self.breakpoint_service = breakpoint_service

    async def execute(
        self,
        session_id: UUID,
        task_id: UUID,
        original_request: str,
        max_context_tokens: int,
        stream: bool = False,
        breakpoint_enabled: bool = False,
        breakpoint_nodes: list[str] | None = None,
    ) -> None:
        """Execute a task workflow.

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
            # Update task status to IN_PROGRESS
            async for db_session in get_db_session():
                task_repo = TaskRepository(db_session)
                await task_repo.update(task_id, status=TaskStatus.IN_PROGRESS.value)
                await db_session.commit()
                break

            # Notify task started (streaming only)
            if stream:
                previous_milestones = await self._get_previous_milestones(session_id)
                await self.notifier.notify_started(
                    session_id=session_id,
                    task_id=task_id,
                    original_request=original_request,
                    previous_milestones=previous_milestones,
                )

            # Execute workflow
            async for db_session in get_db_session():
                runner = WorkflowRunner(
                    db_session,
                    ws_manager=self.notifier.ws_manager,
                    cache=self.cache,
                    event_bus=self.event_bus,
                    breakpoint_service=self.breakpoint_service,
                )

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
                    return

                # Calculate duration
                duration = (datetime.now(UTC) - start_time).total_seconds()

                # Get token counts and cost from state
                total_input_tokens = final_state.get("total_input_tokens", 0)
                total_output_tokens = final_state.get("total_output_tokens", 0)
                total_cost = Decimal(final_state.get("total_cost_usd", "0"))

                # Check if task failed
                task_status = final_state.get("task_status")
                if task_status == TaskStatus.FAILED:
                    await self._handle_failure(
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

                # Task completed successfully
                final_result = self._extract_final_result(final_state)

                logger.info(
                    "task_completed_tokens",
                    task_id=str(task_id),
                    input_tokens=total_input_tokens,
                    output_tokens=total_output_tokens,
                    total_cost=str(total_cost),
                )

                # Update task and session
                await self._finalize_success(
                    db_session=db_session,
                    session_id=session_id,
                    task_id=task_id,
                    final_result=final_result,
                    final_state=final_state,
                    total_input_tokens=total_input_tokens,
                    total_output_tokens=total_output_tokens,
                    total_cost=total_cost,
                )

                # Notify completion
                if stream:
                    total_tokens = total_input_tokens + total_output_tokens
                    await self.notifier.notify_completed(
                        session_id=session_id,
                        task_id=task_id,
                        final_result=final_result,
                        total_tokens=total_tokens,
                        total_cost_usd=total_cost,
                        duration_seconds=duration,
                    )

        except Exception as e:
            logger.exception(
                "task_execution_failed",
                task_id=str(task_id),
                error=str(e),
            )

            if stream:
                await self.notifier.notify_failed(
                    session_id=session_id,
                    task_id=task_id,
                    error=str(e),
                )

            # Update task status to FAILED
            async for db_session in get_db_session():
                task_repo = TaskRepository(db_session)
                await task_repo.update(
                    task_id,
                    status=TaskStatus.FAILED.value,
                    final_result=str(e),
                )
                await db_session.commit()

            self.breakpoint_service.cleanup_task(task_id)

    async def resume(
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
            async for db_session in get_db_session():
                runner = WorkflowRunner(
                    db_session,
                    ws_manager=self.notifier.ws_manager,
                    cache=self.cache,
                    event_bus=self.event_bus,
                    breakpoint_service=self.breakpoint_service,
                )

                # Prepare resume input
                resume_data = None
                if user_input is not None or rejected:
                    resume_data = {
                        "user_input": user_input,
                        "rejected": rejected,
                    }
                    if rejected and not user_input:
                        resume_data["reason"] = "Task cancelled by user"

                # Resume workflow
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

                # Check if interrupted again
                if result.interrupted:
                    logger.info(
                        "task_paused_at_breakpoint_after_resume",
                        task_id=str(task_id),
                        interrupt_node=result.interrupt_node,
                    )
                    return

                # Handle completion
                task_status = final_state.get("task_status")
                total_input_tokens = final_state.get("total_input_tokens", 0)
                total_output_tokens = final_state.get("total_output_tokens", 0)
                total_cost = Decimal(final_state.get("total_cost_usd", "0"))

                if task_status == TaskStatus.FAILED:
                    await self._handle_failure(
                        db_session=db_session,
                        session_id=session_id,
                        task_id=task_id,
                        final_state=final_state,
                        total_input_tokens=total_input_tokens,
                        total_output_tokens=total_output_tokens,
                        total_cost=total_cost,
                        stream=True,
                    )
                    return

                # Success
                final_result = self._extract_final_result(final_state)

                task_repo = TaskRepository(db_session)
                await task_repo.update(
                    task_id,
                    status=TaskStatus.COMPLETED.value,
                    final_result=final_result,
                )
                await db_session.commit()

                self.breakpoint_service.cleanup_task(task_id)

                # Notify completion
                total_tokens = total_input_tokens + total_output_tokens
                await self.notifier.notify_completed(
                    session_id=session_id,
                    task_id=task_id,
                    final_result=final_result,
                    total_tokens=total_tokens,
                    total_cost_usd=total_cost,
                    duration_seconds=0,  # Not tracked for resumed tasks
                )

        except Exception as e:
            logger.exception(
                "task_resume_execution_failed",
                task_id=str(task_id),
                error=str(e),
            )

            self.breakpoint_service.cleanup_task(task_id)

            # Notify failure
            async for db_session in get_db_session():
                task_repo = TaskRepository(db_session)
                task = await task_repo.get_by_id(task_id)
                if task:
                    await self.notifier.notify_failed(
                        session_id=task.session_id,
                        task_id=task_id,
                        error=str(e),
                    )
                break

    async def _get_previous_milestones(self, session_id: UUID) -> list[PreviousMilestoneInfo]:
        """Get previous milestones for session continuity."""
        from agent.api.schemas import PreviousMilestoneInfo

        async for db_session in get_db_session():
            milestone_repo = MilestoneRepository(db_session)
            db_milestones = await milestone_repo.get_by_session_id(session_id)
            return [
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
        return []

    def _extract_final_result(self, final_state: AgentState) -> str:
        """Extract final result from workflow state."""
        final_result_raw = final_state.get("final_response", "")
        final_result = str(final_result_raw) if final_result_raw else ""
        if not final_result:
            milestones = final_state.get("milestones", [])
            if milestones and isinstance(milestones, list):
                last_milestone = milestones[-1]
                if isinstance(last_milestone, dict):
                    worker_output = last_milestone.get("worker_output", "")
                    final_result = str(worker_output) if worker_output else ""
        return final_result

    async def _finalize_success(
        self,
        db_session: AsyncSession,
        session_id: UUID,
        task_id: UUID,
        final_result: str,
        final_state: AgentState,
        total_input_tokens: int,
        total_output_tokens: int,
        total_cost: Decimal,
    ) -> None:
        """Finalize successful task execution."""
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

        # Cache context for next task
        await self._save_context_to_cache(session_id, final_state)

        # Cleanup breakpoint state
        self.breakpoint_service.cleanup_task(task_id)

    async def _handle_failure(
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
        """Handle task failure."""
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

        self.breakpoint_service.cleanup_task(task_id)

        # Notify failure (streaming only)
        if stream:
            current_idx = final_state.get("current_milestone_index", 0)
            await self.notifier.notify_failed(
                session_id=session_id,
                task_id=task_id,
                error=error_message or "Unknown error",
                failed_milestone=current_idx + 1,
            )

    async def _save_context_to_cache(
        self,
        session_id: UUID,
        final_state: AgentState,
    ) -> None:
        """Save conversation context to cache for session continuity."""
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

        # Convert ChatMessage objects to dicts
        messages_data = [{"role": msg.role, "content": msg.content} for msg in context_messages]

        # Use longer TTL for session context (2 hours)
        await self.cache.cache_context(
            session_id=session_id,
            context=messages_data,
            token_count=token_count,
            summary=context_summary,
            ttl=7200,
        )

        logger.info(
            "context_saved_to_cache",
            session_id=str(session_id),
            message_count=len(messages_data),
            has_summary=context_summary is not None,
            token_count=token_count,
        )
