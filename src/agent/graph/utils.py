"""Graph utility functions for project plan operations.

Provides helper functions for navigating and manipulating project plans
during workflow execution.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agent.db.models.project_plan import ProjectPlan
    from agent.graph.state import MilestoneData


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


def find_next_pending_task(tasks: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Find next task that can be executed.

    Considers dependencies - returns task with all dependencies completed.
    Tasks are processed in order, respecting dependency constraints.

    Args:
        tasks: List of task dictionaries from plan_data

    Returns:
        Next executable task dict or None if all done/blocked
    """
    completed_ids = {t["id"] for t in tasks if t.get("status") == "completed"}

    for task in tasks:
        if task.get("status") == "pending":
            deps = task.get("dependencies", [])
            if all(dep in completed_ids for dep in deps):
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


def convert_plan_to_milestones(project_plan: ProjectPlan) -> list[MilestoneData]:
    """Convert project plan tasks to legacy milestone format.

    Provides backward compatibility by converting new project plan
    task structure to the existing MilestoneData format.

    Args:
        project_plan: ProjectPlan model instance

    Returns:
        List of MilestoneData dicts for legacy compatibility
    """
    from uuid import uuid4

    from agent.db.models.enums import MilestoneStatus, TaskComplexity

    from .state import MilestoneData as MilestoneDataType

    tasks = get_tasks_from_plan(project_plan)
    milestones: list[MilestoneDataType] = []

    for task in tasks:
        # Map task complexity string to enum
        complexity_str = task.get("complexity", "MODERATE")
        try:
            complexity = TaskComplexity[complexity_str]
        except KeyError:
            complexity = TaskComplexity.MODERATE

        # Map task status to milestone status
        task_status = task.get("status", "pending")
        if task_status == "completed":
            status = MilestoneStatus.PASSED
        elif task_status == "in_progress":
            status = MilestoneStatus.IN_PROGRESS
        elif task_status == "failed":
            status = MilestoneStatus.FAILED
        else:
            status = MilestoneStatus.PENDING

        milestone: MilestoneDataType = {
            "id": uuid4(),  # Generate new ID for milestone
            "description": task.get("description", ""),
            "complexity": complexity,
            "acceptance_criteria": task.get("acceptance_criteria", ""),
            "status": status,
            "selected_model": None,
            "generated_prompt": None,
            "worker_output": None,
            "qa_feedback": None,
            "retry_count": 0,
        }
        milestones.append(milestone)

    return milestones


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


def apply_task_modifications(
    plan_data: dict[str, Any],
    modifications: list[Any],
) -> dict[str, Any]:
    """Apply task modifications from Architect replan output.

    Supports add, update, and remove operations on tasks.

    Args:
        plan_data: Original plan_data dict
        modifications: List of PlanTaskModification objects

    Returns:
        New plan_data dict with modifications applied
    """
    tasks = list(plan_data.get("tasks", []))

    for mod in modifications:
        action = mod.action if hasattr(mod, "action") else mod.get("action")
        task_id = mod.task_id if hasattr(mod, "task_id") else mod.get("task_id")

        if action == "add" and hasattr(mod, "task") and mod.task:
            # Add new task
            new_task = mod.task.model_dump() if hasattr(mod.task, "model_dump") else mod.task
            new_task["status"] = "pending"
            tasks.append(new_task)

        elif action == "update" and hasattr(mod, "task") and mod.task:
            # Update existing task
            updated_task = mod.task.model_dump() if hasattr(mod.task, "model_dump") else mod.task
            for i, task in enumerate(tasks):
                if task.get("id") == task_id:
                    # Preserve status during update
                    updated_task["status"] = task.get("status", "pending")
                    tasks[i] = updated_task
                    break

        elif action == "remove":
            # Remove task
            tasks = [t for t in tasks if t.get("id") != task_id]

    return {**plan_data, "tasks": tasks}


__all__ = [
    "get_task_by_id",
    "find_next_pending_task",
    "get_task_index",
    "get_tasks_from_plan",
    "convert_plan_to_milestones",
    "update_task_status",
    "apply_task_modifications",
]
