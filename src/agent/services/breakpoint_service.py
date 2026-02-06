"""Breakpoint Service for managing execution breakpoints.

Provides flexible breakpoint control at different granularities:
- Task level: Pause after each task
- Feature level: Pause after each feature completion
- Epic level: Pause after each epic completion
- Specific task IDs: Pause at designated tasks

Also manages the state of HITL (Human-in-the-Loop) breakpoints,
including enabling/disabling breakpoints and tracking pause states.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeAlias
from uuid import UUID

import structlog

from agent.llm.schemas import BreakpointConfig, PauseLevel

if TYPE_CHECKING:
    pass

logger = structlog.get_logger()

# Type alias for project plan data dict structure
# Contains: tasks, features (optional), epics (optional)
ProjectPlanData: TypeAlias = dict[str, Any]


class BreakpointService:
    """Service for evaluating breakpoint conditions.

    Handles:
    - Evaluating pause conditions based on BreakpointConfig
    - Pause level logic (NONE, TASK, FEATURE, EPIC)
    - Specific task_id pause points
    - Failure-based pausing
    - Legacy milestone-based breakpoint state management
    """

    def __init__(self, config: BreakpointConfig | None = None) -> None:
        """Initialize breakpoint service.

        Args:
            config: Breakpoint configuration. If None, uses default config.
        """
        self.config = config or BreakpointConfig()

        # Legacy: Track breakpoint enabled status per task (for milestone-based)
        self._breakpoint_enabled: dict[UUID, bool] = {}

        # Legacy: Track which milestone each task is paused at
        self._paused_at: dict[UUID, int | None] = {}

    def should_pause_after_task(
        self,
        task_id: str,
        task_status: str,
        plan_data: ProjectPlanData,
    ) -> tuple[bool, str | None]:
        """Check if execution should pause after a task.

        Args:
            task_id: Completed task ID (e.g., "T1.1.1")
            task_status: Task completion status ("completed" or "failed")
            plan_data: Full plan data containing tasks, features, epics

        Returns:
            Tuple of (should_pause, reason)
        """
        # Check failure pause
        if task_status == "failed" and self.config.pause_on_failure:
            logger.info(
                "breakpoint_pause_on_failure",
                task_id=task_id,
            )
            return True, f"Task {task_id} failed"

        # Check specific task ID pause
        if task_id in self.config.pause_on_task_ids:
            logger.info(
                "breakpoint_pause_on_task_id",
                task_id=task_id,
            )
            return True, f"Breakpoint at task {task_id}"

        # Check pause level
        pause_level = self._normalize_pause_level(self.config.pause_level)

        if pause_level == PauseLevel.NONE:
            return False, None

        if pause_level == PauseLevel.TASK:
            return True, f"Task {task_id} completed (pause_level: task)"

        if pause_level == PauseLevel.FEATURE:
            # Check if this task completes a feature
            if self._is_feature_completed(task_id, plan_data):
                feature_id = self._get_parent_feature_id(task_id, plan_data)
                return True, f"Feature {feature_id} completed"
            return False, None

        if pause_level == PauseLevel.EPIC:
            # Check if this task completes an epic
            if self._is_epic_completed(task_id, plan_data):
                epic_id = self._get_parent_epic_id(task_id, plan_data)
                return True, f"Epic {epic_id} completed"
            return False, None

        return False, None

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

    def _is_feature_completed(self, task_id: str, plan_data: ProjectPlanData) -> bool:
        """Check if completing this task completes a feature.

        A feature is completed when all its tasks are completed.

        Args:
            task_id: The task ID that was just completed
            plan_data: Full plan data

        Returns:
            True if the feature containing this task is now complete
        """
        tasks = plan_data.get("tasks", [])
        features = plan_data.get("features", [])

        if not features:
            return False

        # Find the task's parent feature
        task = next((t for t in tasks if t["id"] == task_id), None)
        if not task or not task.get("parent_feature_id"):
            return False

        feature_id = task["parent_feature_id"]

        # Get all tasks in this feature
        feature_tasks = [t for t in tasks if t.get("parent_feature_id") == feature_id]

        # Check if all tasks are completed (the current task counts as completed)
        return all(t["status"] == "completed" or t["id"] == task_id for t in feature_tasks)

    def _is_epic_completed(self, task_id: str, plan_data: ProjectPlanData) -> bool:
        """Check if completing this task completes an epic.

        An epic is completed when all its tasks are completed.

        Args:
            task_id: The task ID that was just completed
            plan_data: Full plan data

        Returns:
            True if the epic containing this task is now complete
        """
        tasks = plan_data.get("tasks", [])
        epics = plan_data.get("epics", [])

        if not epics:
            return False

        # Find the task's parent epic
        task = next((t for t in tasks if t["id"] == task_id), None)
        if not task or not task.get("parent_epic_id"):
            return False

        epic_id = task["parent_epic_id"]

        # Get all tasks in this epic
        epic_tasks = [t for t in tasks if t.get("parent_epic_id") == epic_id]

        # Check if all tasks are completed (the current task counts as completed)
        return all(t["status"] == "completed" or t["id"] == task_id for t in epic_tasks)

    def _get_parent_feature_id(self, task_id: str, plan_data: ProjectPlanData) -> str | None:
        """Get parent feature ID for a task.

        Args:
            task_id: Task ID to look up
            plan_data: Full plan data

        Returns:
            Parent feature ID or None if not found
        """
        tasks = plan_data.get("tasks", [])
        task = next((t for t in tasks if t["id"] == task_id), None)
        return task.get("parent_feature_id") if task else None

    def _get_parent_epic_id(self, task_id: str, plan_data: ProjectPlanData) -> str | None:
        """Get parent epic ID for a task.

        Args:
            task_id: Task ID to look up
            plan_data: Full plan data

        Returns:
            Parent epic ID or None if not found
        """
        tasks = plan_data.get("tasks", [])
        task = next((t for t in tasks if t["id"] == task_id), None)
        return task.get("parent_epic_id") if task else None

    def get_pause_summary(self, plan_data: ProjectPlanData) -> dict[str, Any]:
        """Get summary of pause points in the plan.

        Useful for frontend to show where breakpoints will occur.

        Args:
            plan_data: Full plan data containing tasks, features, epics

        Returns:
            Summary dict with pause_level, pause_on_failure, pause_points, etc.
        """
        tasks = plan_data.get("tasks", [])
        features = plan_data.get("features", [])
        epics = plan_data.get("epics", [])

        pause_points: list[dict[str, Any]] = []
        pause_level = self._normalize_pause_level(self.config.pause_level)

        if pause_level == PauseLevel.TASK:
            pause_points = [{"type": "task", "id": t["id"]} for t in tasks]

        elif pause_level == PauseLevel.FEATURE:
            # Find last task of each feature
            for feature in features or []:
                feature_tasks = [t for t in tasks if t.get("parent_feature_id") == feature["id"]]
                if feature_tasks:
                    # Assuming tasks are ordered
                    last_task = feature_tasks[-1]
                    pause_points.append(
                        {
                            "type": "feature",
                            "id": feature["id"],
                            "after_task": last_task["id"],
                        }
                    )

        elif pause_level == PauseLevel.EPIC:
            # Find last task of each epic
            for epic in epics or []:
                epic_tasks = [t for t in tasks if t.get("parent_epic_id") == epic["id"]]
                if epic_tasks:
                    last_task = epic_tasks[-1]
                    pause_points.append(
                        {
                            "type": "epic",
                            "id": epic["id"],
                            "after_task": last_task["id"],
                        }
                    )

        # Add specific task IDs
        for specific_task_id in self.config.pause_on_task_ids:
            pause_points.append({"type": "specific", "id": specific_task_id})

        return {
            "pause_level": pause_level.value,
            "pause_on_failure": self.config.pause_on_failure,
            "pause_on_plan_review": self.config.pause_on_plan_review,
            "pause_points": pause_points,
            "total_pause_points": len(pause_points),
        }

    # =========================================================================
    # Legacy milestone-based breakpoint state management
    # =========================================================================

    def is_breakpoint_enabled(self, task_uuid: UUID) -> bool:
        """Check if breakpoints are enabled for a task.

        Args:
            task_uuid: Task UUID

        Returns:
            True if breakpoints are enabled
        """
        return self._breakpoint_enabled.get(task_uuid, False)

    def set_breakpoint_enabled(self, task_uuid: UUID, enabled: bool) -> None:
        """Enable or disable breakpoints for a task.

        Args:
            task_uuid: Task UUID
            enabled: Whether breakpoints should be enabled
        """
        self._breakpoint_enabled[task_uuid] = enabled
        logger.debug(
            "breakpoint_enabled_changed",
            task_id=str(task_uuid),
            enabled=enabled,
        )

    def is_paused_at(self, task_uuid: UUID, milestone_index: int) -> bool:
        """Check if a task is paused at a specific milestone.

        Args:
            task_uuid: Task UUID
            milestone_index: Milestone index to check

        Returns:
            True if the task is paused at this milestone
        """
        return self._paused_at.get(task_uuid) == milestone_index

    def set_paused_at(self, task_uuid: UUID, milestone_index: int | None) -> None:
        """Set which milestone a task is paused at.

        Args:
            task_uuid: Task UUID
            milestone_index: Milestone index (None to clear)
        """
        if milestone_index is None:
            self._paused_at.pop(task_uuid, None)
            logger.debug("breakpoint_cleared", task_id=str(task_uuid))
        else:
            self._paused_at[task_uuid] = milestone_index
            logger.debug(
                "breakpoint_paused_at",
                task_id=str(task_uuid),
                milestone_index=milestone_index,
            )

    def clear_paused_at(self, task_uuid: UUID) -> None:
        """Clear the paused state for a task.

        Args:
            task_uuid: Task UUID
        """
        self.set_paused_at(task_uuid, None)

    def cleanup_task(self, task_uuid: UUID) -> None:
        """Clean up all breakpoint state for a task.

        Call this when a task completes or is cancelled.

        Args:
            task_uuid: Task UUID
        """
        self._breakpoint_enabled.pop(task_uuid, None)
        self._paused_at.pop(task_uuid, None)
        logger.debug("breakpoint_task_cleanup", task_id=str(task_uuid))

    def get_state(self, task_uuid: UUID) -> dict[str, Any] | None:
        """Get current breakpoint state for a task.

        Args:
            task_uuid: Task UUID

        Returns:
            State dict with paused status and reason, or None if not paused
        """
        milestone_index = self._paused_at.get(task_uuid)
        if milestone_index is not None:
            return {
                "paused": True,
                "milestone_index": milestone_index,
                "reason": f"Paused at milestone {milestone_index}",
            }
        return None

    def update_config(self, config: BreakpointConfig) -> None:
        """Update the breakpoint configuration.

        Args:
            config: New breakpoint configuration
        """
        self.config = config
        logger.info(
            "breakpoint_config_updated",
            pause_level=config.pause_level,
            pause_on_plan_review=config.pause_on_plan_review,
            pause_on_failure=config.pause_on_failure,
        )
