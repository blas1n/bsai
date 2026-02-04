"""Parallel Execution Engine.

Executes tasks in parallel based on dependency graph.
Provides breakpoint support and execution state management.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from enum import Enum
from typing import TYPE_CHECKING, Any

import structlog

from agent.llm.schemas import BreakpointConfig, PauseLevel
from agent.services.dependency_graph import DependencyGraph

if TYPE_CHECKING:
    pass

logger = structlog.get_logger()


class ExecutionStatus(str, Enum):
    """Execution engine status."""

    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class ExecutionEngine:
    """Engine for parallel task execution.

    Manages parallel execution of tasks based on a dependency graph,
    respecting max parallelism limits and breakpoint configurations.

    Example:
        >>> graph = DependencyGraph(tasks)
        >>> engine = ExecutionEngine(graph, max_parallel=3)
        >>> results = await engine.execute_all(my_task_executor)
    """

    def __init__(
        self,
        graph: DependencyGraph,
        breakpoint_config: BreakpointConfig | None = None,
        max_parallel: int = 5,
    ) -> None:
        """Initialize execution engine.

        Args:
            graph: Dependency graph defining task dependencies
            breakpoint_config: Optional breakpoint configuration for HITL support
            max_parallel: Maximum number of tasks to execute in parallel
        """
        self.graph = graph
        self.breakpoint_config = breakpoint_config or BreakpointConfig()
        self.max_parallel = max_parallel

        # Execution state
        self._status = ExecutionStatus.IDLE
        self._paused = False
        self._pause_reason: str | None = None
        self._pause_event = asyncio.Event()
        self._pause_event.set()  # Not paused initially

        # Results storage
        self._results: dict[str, dict[str, Any]] = {}

        # Execution tracking
        self._completed_count = 0
        self._failed_count = 0
        self._semaphore: asyncio.Semaphore | None = None

    async def execute_all(
        self,
        task_executor: Callable[[str], Awaitable[dict[str, Any]]],
        on_task_complete: Callable[[str, dict[str, Any]], Awaitable[None]] | None = None,
    ) -> dict[str, Any]:
        """Execute all tasks respecting dependencies.

        Uses asyncio.gather for parallel execution of tasks that have
        no unmet dependencies. Respects max_parallel limit using a semaphore.

        Args:
            task_executor: Async function to execute a single task.
                Takes task_id and returns result dict.
            on_task_complete: Optional callback invoked after each task completes.
                Receives task_id and result dict.

        Returns:
            Execution results dict with:
                - status: Overall execution status
                - results: Dict of task_id -> result
                - stats: Execution statistics

        Raises:
            RuntimeError: If execution is already running
        """
        if self._status == ExecutionStatus.RUNNING:
            raise RuntimeError("Execution is already running")

        self._status = ExecutionStatus.RUNNING
        self._semaphore = asyncio.Semaphore(self.max_parallel)
        self._results = {}
        self._completed_count = 0
        self._failed_count = 0

        logger.info(
            "execution_started",
            total_tasks=len(self.graph.nodes),
            max_parallel=self.max_parallel,
        )

        try:
            while not self.graph.is_all_completed():
                # Wait if paused
                await self._pause_event.wait()

                # Check if execution was cancelled while paused
                if self._status == ExecutionStatus.FAILED:
                    break

                # Get tasks ready to execute
                ready_tasks = self.graph.get_ready_tasks()

                if not ready_tasks:
                    # No ready tasks but not all completed - check for blocked
                    blocked = self.graph.get_blocked_tasks()
                    if blocked:
                        logger.warning(
                            "execution_blocked",
                            blocked_tasks=blocked,
                        )
                        # Mark blocked tasks as failed
                        for task_id in blocked:
                            self.graph.mark_failed(task_id)
                            self._results[task_id] = {
                                "success": False,
                                "error": "Blocked by failed dependency",
                            }
                            self._failed_count += 1
                        continue
                    else:
                        # All in-progress tasks will eventually complete
                        # Wait a bit and check again
                        await asyncio.sleep(0.1)
                        continue

                # Execute ready tasks in parallel
                async_tasks = [
                    self._execute_task_with_semaphore(
                        task_id,
                        task_executor,
                        on_task_complete,
                    )
                    for task_id in ready_tasks
                ]

                # Use gather to run tasks concurrently
                await asyncio.gather(*async_tasks, return_exceptions=True)

            # Determine final status
            if self._failed_count > 0:
                self._status = ExecutionStatus.COMPLETED  # Completed with failures
            else:
                self._status = ExecutionStatus.COMPLETED

            logger.info(
                "execution_completed",
                completed=self._completed_count,
                failed=self._failed_count,
                status=self._status.value,
            )

        except Exception as e:
            self._status = ExecutionStatus.FAILED
            logger.error("execution_failed", error=str(e))
            raise

        return {
            "status": self._status.value,
            "results": self._results,
            "stats": self.graph.get_stats(),
        }

    async def _execute_task_with_semaphore(
        self,
        task_id: str,
        executor: Callable[[str], Awaitable[dict[str, Any]]],
        on_complete: Callable[[str, dict[str, Any]], Awaitable[None]] | None,
    ) -> None:
        """Execute a task with semaphore for parallelism limiting.

        Args:
            task_id: ID of the task to execute
            executor: Async function to execute the task
            on_complete: Optional callback after completion
        """
        async with self._semaphore:  # type: ignore[union-attr]
            await self._execute_task(task_id, executor, on_complete)

    async def _execute_task(
        self,
        task_id: str,
        executor: Callable[[str], Awaitable[dict[str, Any]]],
        on_complete: Callable[[str, dict[str, Any]], Awaitable[None]] | None,
    ) -> None:
        """Execute a single task.

        Args:
            task_id: ID of the task to execute
            executor: Async function to execute the task
            on_complete: Optional callback after completion
        """
        # Mark task as in progress
        self.graph.mark_in_progress(task_id)

        logger.debug("task_execution_started", task_id=task_id)

        try:
            # Execute the task
            result = await executor(task_id)

            # Store result
            self._results[task_id] = result

            # Determine success
            success = result.get("success", True)

            if success:
                self.graph.mark_completed(task_id)
                self._completed_count += 1
                logger.debug("task_execution_succeeded", task_id=task_id)
            else:
                self.graph.mark_failed(task_id)
                self._failed_count += 1
                logger.warning(
                    "task_execution_failed",
                    task_id=task_id,
                    error=result.get("error"),
                )

            # Call completion callback
            if on_complete:
                await on_complete(task_id, result)

            # Check breakpoint after successful completion
            if success and self._check_breakpoint(task_id, result):
                self._pause("breakpoint")

        except Exception as e:
            # Handle unexpected errors
            error_result: dict[str, Any] = {
                "success": False,
                "error": str(e),
            }
            self._results[task_id] = error_result
            self.graph.mark_failed(task_id)
            self._failed_count += 1

            logger.error(
                "task_execution_error",
                task_id=task_id,
                error=str(e),
            )

            # Call completion callback even on error
            if on_complete:
                await on_complete(task_id, error_result)

            # Check if should pause on failure
            if self.breakpoint_config.pause_on_failure:
                self._pause(f"Task {task_id} failed: {e}")

    def _check_breakpoint(self, task_id: str, result: dict[str, Any]) -> bool:
        """Check if execution should pause after task completion.

        Args:
            task_id: Completed task ID
            result: Task execution result

        Returns:
            True if execution should pause
        """
        # Check specific task IDs
        if task_id in self.breakpoint_config.pause_on_task_ids:
            self._pause_reason = f"Breakpoint at task {task_id}"
            return True

        # Check pause level
        pause_level = self._normalize_pause_level(self.breakpoint_config.pause_level)

        if pause_level == PauseLevel.TASK:
            self._pause_reason = f"Task {task_id} completed (pause_level: task)"
            return True

        # For FEATURE and EPIC levels, we need plan_data context
        # which isn't available in the basic engine. These are handled
        # by the BreakpointService with full plan context.

        return False

    def _normalize_pause_level(self, pause_level: str | PauseLevel) -> PauseLevel:
        """Normalize pause level to PauseLevel enum.

        Args:
            pause_level: Pause level as string or enum

        Returns:
            PauseLevel enum value
        """
        if isinstance(pause_level, PauseLevel):
            return pause_level
        return PauseLevel(pause_level)

    def _pause(self, reason: str) -> None:
        """Pause execution.

        Args:
            reason: Reason for pausing
        """
        self._paused = True
        self._pause_reason = reason
        self._pause_event.clear()
        self._status = ExecutionStatus.PAUSED

        logger.info(
            "execution_paused",
            reason=reason,
        )

    def resume(self) -> None:
        """Resume paused execution.

        Clears the pause state and allows execution to continue.
        """
        if not self._paused:
            logger.debug("execution_resume_not_paused")
            return

        self._paused = False
        self._pause_reason = None
        self._status = ExecutionStatus.RUNNING
        self._pause_event.set()

        logger.info("execution_resumed")

    def cancel(self) -> None:
        """Cancel execution.

        Sets execution to failed status and resumes any waiting tasks
        so they can exit gracefully.
        """
        self._status = ExecutionStatus.FAILED
        self._paused = False
        self._pause_event.set()  # Unblock any waiting

        logger.info("execution_cancelled")

    def get_status(self) -> dict[str, Any]:
        """Get current execution status.

        Returns:
            Status dict containing:
                - status: Current execution status (idle/running/paused/completed/failed)
                - paused: Whether execution is paused
                - pause_reason: Reason for pause (if paused)
                - stats: Graph statistics (completed/failed/pending counts)
                - results: Task results dict
        """
        return {
            "status": self._status.value,
            "paused": self._paused,
            "pause_reason": self._pause_reason,
            "stats": self.graph.get_stats(),
            "results": self._results,
        }

    @property
    def is_paused(self) -> bool:
        """Check if execution is currently paused.

        Returns:
            True if paused
        """
        return self._paused

    @property
    def is_running(self) -> bool:
        """Check if execution is currently running.

        Returns:
            True if running (including paused state)
        """
        return self._status in (ExecutionStatus.RUNNING, ExecutionStatus.PAUSED)

    @property
    def is_completed(self) -> bool:
        """Check if execution is completed.

        Returns:
            True if completed (success or failure)
        """
        return self._status in (ExecutionStatus.COMPLETED, ExecutionStatus.FAILED)
