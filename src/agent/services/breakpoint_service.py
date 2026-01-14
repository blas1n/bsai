"""Breakpoint state management service.

Manages the state of HITL (Human-in-the-Loop) breakpoints,
including enabling/disabling breakpoints and tracking pause states.
"""

from __future__ import annotations

from uuid import UUID

import structlog

logger = structlog.get_logger()


class BreakpointService:
    """Service for managing breakpoint state.

    Handles:
    - Enabling/disabling breakpoints per task
    - Tracking which milestone a task is paused at
    - Clearing pause state on resume/rejection
    """

    def __init__(self) -> None:
        """Initialize the breakpoint service."""
        # Track breakpoint enabled status per task
        self._breakpoint_enabled: dict[UUID, bool] = {}

        # Track which milestone each task is paused at
        self._paused_at: dict[UUID, int | None] = {}

    def is_breakpoint_enabled(self, task_id: UUID) -> bool:
        """Check if breakpoints are enabled for a task.

        Args:
            task_id: Task UUID

        Returns:
            True if breakpoints are enabled
        """
        return self._breakpoint_enabled.get(task_id, False)

    def set_breakpoint_enabled(self, task_id: UUID, enabled: bool) -> None:
        """Enable or disable breakpoints for a task.

        Args:
            task_id: Task UUID
            enabled: Whether breakpoints should be enabled
        """
        self._breakpoint_enabled[task_id] = enabled
        logger.debug(
            "breakpoint_enabled_changed",
            task_id=str(task_id),
            enabled=enabled,
        )

    def is_paused_at(self, task_id: UUID, milestone_index: int) -> bool:
        """Check if a task is paused at a specific milestone.

        Args:
            task_id: Task UUID
            milestone_index: Milestone index to check

        Returns:
            True if the task is paused at this milestone
        """
        return self._paused_at.get(task_id) == milestone_index

    def set_paused_at(self, task_id: UUID, milestone_index: int | None) -> None:
        """Set which milestone a task is paused at.

        Args:
            task_id: Task UUID
            milestone_index: Milestone index (None to clear)
        """
        if milestone_index is None:
            self._paused_at.pop(task_id, None)
            logger.debug("breakpoint_cleared", task_id=str(task_id))
        else:
            self._paused_at[task_id] = milestone_index
            logger.debug(
                "breakpoint_paused_at",
                task_id=str(task_id),
                milestone_index=milestone_index,
            )

    def clear_paused_at(self, task_id: UUID) -> None:
        """Clear the paused state for a task.

        Args:
            task_id: Task UUID
        """
        self.set_paused_at(task_id, None)

    def cleanup_task(self, task_id: UUID) -> None:
        """Clean up all breakpoint state for a task.

        Call this when a task completes or is cancelled.

        Args:
            task_id: Task UUID
        """
        self._breakpoint_enabled.pop(task_id, None)
        self._paused_at.pop(task_id, None)
        logger.debug("breakpoint_task_cleanup", task_id=str(task_id))
