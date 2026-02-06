"""Graph utility functions for project plan operations.

Provides helper functions for navigating and manipulating project plans
during workflow execution.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from bsai.db.models.project_plan import ProjectPlan


def get_task_by_id(tasks: list[dict[str, Any]], task_id: str) -> dict[str, Any] | None:
    """Find task by ID in task list.

    Args:
        tasks: List of task dictionaries from plan_data
        task_id: Task ID to find (e.g., "T1.1.1")

    Returns:
        Task dict or None if not found
    """
    for task in tasks:
        if task.get("id") == task_id:
            return task
    return None


def get_task_index(tasks: list[dict[str, Any]], task_id: str) -> int:
    """Get index of task in list.

    Args:
        tasks: List of task dictionaries
        task_id: Task ID to find

    Returns:
        Index of task, or -1 if not found
    """
    for i, task in enumerate(tasks):
        if task.get("id") == task_id:
            return i
    return -1


def get_tasks_from_plan(project_plan: ProjectPlan) -> list[dict[str, Any]]:
    """Extract tasks list from project plan.

    Args:
        project_plan: ProjectPlan model instance

    Returns:
        List of task dictionaries
    """
    if project_plan.plan_data is None:
        return []
    tasks: list[dict[str, Any]] = project_plan.plan_data.get("tasks", [])
    return tasks


def update_task_status(
    plan_data: dict[str, Any],
    task_id: str,
    new_status: str,
) -> dict[str, Any]:
    """Update a task's status in plan_data.

    Creates a new plan_data dict with the updated task status.

    Args:
        plan_data: Original plan_data dict
        task_id: Task ID to update
        new_status: New status value (e.g., "completed", "in_progress", "failed")

    Returns:
        New plan_data dict with updated task status
    """
    tasks = plan_data.get("tasks", [])
    updated_tasks = []

    for task in tasks:
        if task.get("id") == task_id:
            updated_task = {**task, "status": new_status}
            updated_tasks.append(updated_task)
        else:
            updated_tasks.append(task)

    return {**plan_data, "tasks": updated_tasks}


__all__ = [
    "get_task_by_id",
    "get_task_index",
    "get_tasks_from_plan",
    "update_task_status",
]
